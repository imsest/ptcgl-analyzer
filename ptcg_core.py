"""PTCGL分析アプリのロジック部分（画面以外）。

- デッキリストの解析
- バトルログのターン分割
- Gemini への問い合わせ（形勢評価・アドバイス）
- データの保存/読み込み
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
import time
from typing import Callable, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 形勢評価の定義（-2〜+2 の5段階）
# ---------------------------------------------------------------------------
EVAL_LABELS = {
    2: "優勢",
    1: "やや優勢",
    0: "互角",
    -1: "やや劣勢",
    -2: "劣勢",
}


def eval_label(score: int) -> str:
    return EVAL_LABELS.get(max(-2, min(2, int(score))), "互角")


# ---------------------------------------------------------------------------
# デッキリスト解析（PTCGL のエクスポート形式）
# ---------------------------------------------------------------------------
_CATEGORY_PATTERNS = {
    "pokemon": re.compile(r"^(pok[eé]mon|ポケモン)\s*[:：]", re.I),
    "trainer": re.compile(r"^(trainer|トレーナーズ|グッズ|サポート)\s*[:：]", re.I),
    "energy": re.compile(r"^(energy|エネルギー)\s*[:：]", re.I),
}
_CARD_LINE = re.compile(r"^\*?\s*(\d+)\s+(.+?)\s*$")


def parse_deck(text: str) -> dict:
    """デッキテキストを {pokemon:[...], trainer:[...], energy:[...], total:int} にする。"""
    result = {"pokemon": [], "trainer": [], "energy": [], "other": []}
    current = "other"
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("total cards"):
            continue
        matched_cat = False
        for cat, pat in _CATEGORY_PATTERNS.items():
            if pat.match(line):
                current = cat
                matched_cat = True
                break
        if matched_cat:
            continue
        m = _CARD_LINE.match(line)
        if m:
            result[current].append({"count": int(m.group(1)), "name": m.group(2)})
    counts = {k: sum(c["count"] for c in v) for k, v in result.items()}
    result["counts"] = counts
    result["total"] = sum(counts.values())
    return result


# ---------------------------------------------------------------------------
# バトルログのターン分割
# ---------------------------------------------------------------------------
# 実際のPTCGLログ:          "S_Tobari's Turn"（番号なし）
# 旧形式・表記ゆれにも対応:  "Turn # 3 - PlayerName's Turn" / "○○のターン"
_TURN_HEADER_NUMBERED = re.compile(
    r"^\s*(?:Turn|ターン)\s*#?\s*(\d+)\s*[-–—:：]\s*(.+?)\s*(?:'s Turn|’s Turn|のターン)?\s*$",
    re.I,
)
_TURN_HEADER_PLAIN = re.compile(r"^\s*(\S+?)\s*(?:'s Turn|’s Turn|のターン)\s*$", re.I)


def _match_turn_header(line: str):
    """ターン見出しなら (番号 or None, プレイヤー名) を返す。"""
    m = _TURN_HEADER_NUMBERED.match(line)
    if m:
        return int(m.group(1)), m.group(2).strip()
    m = _TURN_HEADER_PLAIN.match(line)
    if m:
        return None, m.group(1).strip()
    return None


class LogTurn(BaseModel):
    number: int
    player: str
    lines: list[str]


class ParsedLog(BaseModel):
    setup: list[str]
    turns: list[LogTurn]
    players: list[str]
    ending: list[str]

    @property
    def ok(self) -> bool:
        return len(self.turns) > 0


def parse_log(text: str) -> ParsedLog:
    setup: list[str] = []
    turns: list[LogTurn] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        header = _match_turn_header(line)
        if header:
            num, player = header
            turns.append(LogTurn(number=num if num is not None else len(turns) + 1, player=player, lines=[]))
            continue
        if turns:
            turns[-1].lines.append(line.strip())
        else:
            setup.append(line.strip())

    players: list[str] = []
    for t in turns:
        if t.player not in players:
            players.append(t.player)

    # 最後のターンにある勝敗行は ending として切り出す
    ending: list[str] = []
    if turns:
        keep = []
        for line in turns[-1].lines:
            if re.search(r"(wins\.|won the game|conceded|降参|勝利|の勝ち)", line, re.I):
                ending.append(line)
            else:
                keep.append(line)
        turns[-1].lines = keep
    return ParsedLog(setup=setup, turns=turns, players=players, ending=ending)


def format_log_for_ai(parsed: ParsedLog, raw_text: str) -> str:
    """AIに渡しやすいよう、ターン番号つきで整形する。分割できなければ原文のまま。"""
    if not parsed.ok:
        return raw_text
    out = ["[準備フェーズ]"] + parsed.setup
    for t in parsed.turns:
        out.append(f"\n[ターン{t.number}：{t.player}]")
        out.extend(t.lines)
    if parsed.ending:
        out.append("\n[試合終了]")
        out.extend(parsed.ending)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# AI の出力形式（構造化出力）
# ---------------------------------------------------------------------------
class TurnEval(BaseModel):
    turn: int = Field(description="ログ上のターン番号")
    player: str = Field(description="そのターンを行ったプレイヤー。'自分' または '相手'")
    summary: str = Field(description="そのターンに起きたことを1〜2文で要約")
    score: int = Field(description="このターン終了時点の自分視点の形勢。+2優勢,+1やや優勢,0互角,-1やや劣勢,-2劣勢")
    reason: str = Field(description="その評価の根拠（サイド差、盤面、エネルギー、手札資源、山札など）")
    key_actions: list[str] = Field(description="このターンの重要な行動（最大4つ）")
    better_play: str = Field(description="自分のターンでより良い手があれば具体的に。なければ空文字")


class SwingPoint(BaseModel):
    turn: int = Field(description="形勢が悪化した（特に優勢→劣勢）自分のターン、またはその原因となった自分のターン")
    what_happened: str = Field(description="何が起きて形勢が傾いたか")
    better_play: str = Field(description="打つべきだった手。カード名と順番を具体的に")
    why: str = Field(description="その手が良い理由。相手の次ターンの返しも考慮")
    alternative_line: list[str] = Field(description="代替手順を1手ずつ並べたもの")
    confidence: str = Field(description="確度：高/中/低（非公開情報に依存する度合い）")


class GameAnalysis(BaseModel):
    my_name: str
    opponent_name: str
    opponent_deck_guess: str = Field(description="ログから推測される相手のデッキタイプ")
    result: str = Field(description="勝ち / 負け / 不明")
    went_first: str = Field(description="先攻 / 後攻 / 不明（自分視点）")
    overall_summary: str = Field(description="試合全体の流れの総評（3〜5文）")
    turns: list[TurnEval]
    swing_points: list[SwingPoint]
    lessons: list[str] = Field(description="次の試合に活かせる教訓（3〜5個）")


# ---------------------------------------------------------------------------
# レギュレーションと環境の初期値
# ---------------------------------------------------------------------------
DEFAULT_REGULATION = (
    "スタンダード（2026-27シーズン）：レギュレーションマーク H・I・J 以降のカードのみ使用可能。"
    "G マークのカードは 2026年3月26日（PTCGL）／4月10日（公式大会）のローテーションで使用不可。"
)

DEFAULT_META_NOTES = """【初期データ：2026年8月下旬時点の上位デッキ（使用率順）】
1. メガドリュウズex（Mega Excadrill ex）
2. ドラパルトex
3. Festival Lead
4. ドラパルトex / バシャーモex
5. ヤドキング（Slowking）
6. フーディン / ノココッチ（Alakazam / Dudunsparce）
7. ドラパルトex / ヨノワール
8. N のゾロアーク
9. オーロンゲ / ユキメノコ（Grimmsnarl / Froslass）
10. ダダリン（Dhelmise）
※出典：GeekyDomain Standard Meta Tier List（2026-08-31）。「最新の環境を調べる」で更新してください。"""


def today_str() -> str:
    return datetime.now().strftime("%Y年%m月%d日")


def system_prompt(regulation: str) -> str:
    return f"""あなたはポケモンカードゲーム（Pokémon TCG Live / スタンダード）のトッププレイヤー兼コーチです。
将棋の解説者のように、各ターン終了時点の形勢を自分（ユーザー）視点で評価し、悪手と最善手を指摘します。

## 前提（最重要）
- 今日は {today_str()} です。
- 現在のレギュレーション：{regulation}
- あなたの学習データは古い可能性があります。ユーザーが渡す「環境メモ」や検索結果を、自分の記憶より常に優先してください。
- ローテーションで使用不可になったカードや、古い環境のデッキを前提にした助言はしないでください。
  カードが使用可能か自信がない場合は、そう明記してください。

## 評価の観点
- サイドの取り合い（残り枚数、次に何枚取れるか／取られるか、プライズマップ）
- 盤面（育っているアタッカー、ベンチの耐久、ex の数）
- リソース（手札、山札残り、エネルギー、サポート・スタジアムの残り）
- テンポ（次ターンに攻撃できるか、相手の返しの強さ）

## ルール
- 回答はすべて日本語。カード名はログの表記のままでよい。
- 相手の手札など見えない情報は断定せず、確率で語り、確度を示す。
- 「良い手」はログから実行可能だったと判断できる範囲で提案する（手札に無かったカードを前提にしない）。不確かなら前提を明示する。
- 対局の検討（ログ解析）で提案に使うカードは、「自分のデッキリスト」か「バトルログに登場したカード」に含まれるものだけに限定する。
  それ以外のカード名は、記憶にあっても絶対に出さない。（PTCGLのスタンダード戦で使われたカードは、すべて使用可能なカードのため）
- 構築の変更案など、デッキ外のカードを勧めるときは、カード名の後ろに（収録弾・レギュレーションマーク）を必ず書く。
  マークが H 以降だと確認できないカードは勧めない。
- 形勢が +1以上 から -1以下 に落ちた、または2段階以上悪化した場面は必ず swing_points に入れる。
- ターン評価はログの全ターンについて1件ずつ出す。
"""


def build_analysis_prompt(log_text: str, my_name: str, deck_text: str, meta_notes: str, extra_notes: str) -> str:
    parts = [
        f"## 自分のプレイヤー名\n{my_name or '（未設定：ログから推測して）'}",
        f"## 自分のデッキリスト\n{deck_text or '（未登録）'}",
        f"## 現在の環境メモ（最新情報。記憶より優先すること）\n{meta_notes or '（なし）'}",
        f"## ユーザーからの補足（手札の状況など）\n{extra_notes or '（なし）'}",
        f"## バトルログ\n{log_text}",
        "上のバトルログを解析し、指定のJSON形式で出力してください。"
        "「より良い手」「代替手順」で使うカードは、上のデッキリストかバトルログに出てくるカードだけにしてください。",
    ]
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# 形勢の転換点をコード側でも検出（AIの見落とし対策）
# ---------------------------------------------------------------------------
def detect_swings(turns: list[dict]) -> list[int]:
    """スコア列から『優勢→劣勢』や2段階以上の悪化を起こしたターン番号を返す。"""
    swings = []
    prev: Optional[int] = None
    for t in turns:
        s = int(t.get("score", 0))
        if prev is not None and ((prev >= 1 and s <= -1) or (prev - s >= 2)):
            swings.append(int(t["turn"]))
        prev = s
    return swings


# ---------------------------------------------------------------------------
# Gemini 呼び出し（自動リトライ＋モデル切り替えつき）
# ---------------------------------------------------------------------------
FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-flash-latest"]


class AIError(Exception):
    pass


_CLIENTS: dict = {}


def _client(api_key: str):
    """Geminiクライアントを使い回す。

    使い捨てにすると、通信中にクライアントが自動で閉じられて
    「Cannot send a request, as the client has been closed.」になるため、保持しておく。
    """
    from google import genai  # 遅延インポート（テスト時に不要にするため）

    if api_key not in _CLIENTS:
        _CLIENTS[api_key] = genai.Client(api_key=api_key)
    return _CLIENTS[api_key]


def _classify(e: Exception) -> str:
    msg = str(e)
    if "503" in msg or "UNAVAILABLE" in msg or "500" in msg or "INTERNAL" in msg or "overloaded" in msg.lower():
        return "busy"  # 一時的な混雑 → 待って再試行
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        return "quota"  # 無料枠の上限 → 別モデルへ
    if "404" in msg or "NOT_FOUND" in msg:
        return "model"  # モデル名が無い → 別モデルへ
    if "API key" in msg or "API_KEY" in msg or "401" in msg or "403" in msg or "UNAUTHENTICATED" in msg:
        return "auth"
    return "other"


def _error_message(kind: str, raw: str) -> str:
    return {
        "busy": "Geminiのサーバーが混み合っています（Google側の一時的な混雑）。数分おいてからもう一度試してください。",
        "quota": "無料枠の利用上限に達しました。1分ほど待つか、明日もう一度試してください。",
        "model": "選んだモデルが見つかりませんでした。設定でモデルを変更してください。",
        "auth": "APIキーが使えませんでした。Secrets の GEMINI_API_KEY を確認してください。",
    }.get(kind, f"AIの呼び出しに失敗しました：{raw[:300]}")


def _generate(api_key: str, model: str, contents: str, config, notify: Optional[Callable[[str], None]] = None):
    """混雑(503)は待って再試行、上限(429)やモデル不在は別モデルへ切り替える。"""
    models = [model] + [m for m in FALLBACK_MODELS if m != model]
    last_kind, last_raw = "other", ""
    for i, m in enumerate(models):
        for attempt in range(2):
            try:
                resp = _client(api_key).models.generate_content(model=m, contents=contents, config=config)
                return resp, m
            except Exception as e:  # noqa: BLE001
                kind = _classify(e)
                last_kind, last_raw = kind, str(e)
                if kind == "auth":
                    raise AIError(_error_message(kind, str(e))) from e
                if kind == "busy" and attempt == 0:
                    if notify:
                        notify(f"{m} が混雑中。数秒待って再試行しています…")
                    time.sleep(4)
                    continue
                if kind == "other":
                    raise AIError(_error_message(kind, str(e))) from e
                break  # 次のモデルへ
        if i + 1 < len(models) and notify:
            notify(f"{m} が使えないため {models[i + 1]} に切り替えます…")
    raise AIError(_error_message(last_kind, last_raw))


def analyze_game(api_key: str, model: str, prompt: str, regulation: str, notify=None) -> tuple[dict, str]:
    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=system_prompt(regulation),
        response_mime_type="application/json",
        response_schema=GameAnalysis,
        temperature=0.3,
    )
    resp, used = _generate(api_key, model, prompt, config, notify)
    parsed = getattr(resp, "parsed", None)
    if isinstance(parsed, GameAnalysis):
        return parsed.model_dump(), used
    try:
        return GameAnalysis.model_validate_json(resp.text).model_dump(), used
    except Exception as e:  # noqa: BLE001
        raise AIError("AIの返答を読み取れませんでした。もう一度試してください。") from e


def _sources(resp) -> list[dict]:
    """Google検索グラウンディングの参照元を取り出す。"""
    out, seen = [], set()
    try:
        for cand in resp.candidates or []:
            gm = getattr(cand, "grounding_metadata", None)
            for ch in (getattr(gm, "grounding_chunks", None) or []):
                web = getattr(ch, "web", None)
                if web and web.uri and web.uri not in seen:
                    seen.add(web.uri)
                    out.append({"title": web.title or web.uri, "url": web.uri})
    except Exception:  # noqa: BLE001
        pass
    return out


def ask_text(api_key: str, model: str, prompt: str, regulation: str, use_search: bool = True, notify=None) -> dict:
    """自由形式（Markdown）の回答。use_search=True なら Google 検索で最新情報を確認させる。

    返り値: {"text", "model", "searched", "sources", "at"}
    """
    from google.genai import types

    base = dict(system_instruction=system_prompt(regulation), temperature=0.5)
    if use_search:
        try:
            cfg = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())], **base)
            resp, used = _generate(api_key, model, prompt, cfg, notify)
            return {"text": resp.text or "", "model": used, "searched": True,
                    "sources": _sources(resp), "at": datetime.now().strftime("%Y-%m-%d %H:%M")}
        except AIError:
            if notify:
                notify("検索つきで回答できなかったため、検索なしで回答します…")
    resp, used = _generate(api_key, model, prompt, types.GenerateContentConfig(**base), notify)
    return {"text": resp.text or "", "model": used, "searched": False,
            "sources": [], "at": datetime.now().strftime("%Y-%m-%d %H:%M")}


# ---------------------------------------------------------------------------
# プロンプト
# ---------------------------------------------------------------------------
_SEARCH_FIRST = (
    "まず Google 検索で、直近1か月のスタンダード環境（Limitless TCG の大会結果、"
    "公式の禁止・使用可能カード情報など）を確認してから答えてください。"
)


def deck_guide_prompt(deck_text: str, meta_notes: str, focus: str) -> str:
    return f"""{_SEARCH_FIRST}
次のデッキの戦い方を、今の環境に合わせて解説してください。

## デッキリスト
{deck_text}

## 環境メモ（ユーザーが保存した最新情報）
{meta_notes or '（なし）'}

## 特に知りたいこと
{focus or '（特になし）'}

以下の見出し（### を使う）で、カード名と順番を出して具体的に書いてください。
### コンセプトと勝ち筋
### 理想の展開（先攻1ターン目／後攻1ターン目／2ターン目以降）
### 序盤の判断基準（手札・状況別）
### 中盤〜終盤のサイドプラン
### 今の上位デッキとの相性と立ち回り
### よくあるミス
### 構築の見直し候補（使用可能なカードのみ・理由つき）
"""


def meta_advice_prompt(deck_text: str, meta_notes: str) -> str:
    return f"""{_SEARCH_FIRST}
自分のデッキへ、今の環境を踏まえたアドバイスをください。

## 自分のデッキ
{deck_text}

## 環境メモ（ユーザーが保存した最新情報）
{meta_notes or '（なし）'}

以下の見出し（### を使う）で：
### 今の環境での立ち位置（有利・不利な相手）
### 不利な相手への対策（立ち回り・採用カード）
### 構築の調整案（IN / OUT を枚数つきで。使用可能なカードのみ）
### 練習で意識すること
"""


def meta_research_prompt(regulation: str) -> str:
    return f"""今日（{today_str()}）時点の Pokémon TCG スタンダード環境（{regulation}）について、
Google 検索で直近1か月の大会結果（Limitless TCG など）を調べてください。

出力形式（日本語・Markdown）：
- 冒頭に「調査日：{today_str()}」
- 上位デッキ 8〜10個を使用率の高い順に番号つきリストで。各デッキは「デッキ名（日本語名／英語名）— 主なアタッカー — 特徴（1文）」
- 最後に「直近の変更点」（新弾の発売、禁止カード、ルール変更など）があれば箇条書き
"""


def deep_dive_prompt(analysis: dict, turn: int, log_text: str, deck_text: str) -> str:
    return f"""以前の解析結果とバトルログをもとに、ターン{turn}の局面を深掘りしてください。

## 自分のデッキ
{deck_text or '（未登録）'}

## 解析結果（JSON）
{json.dumps(analysis, ensure_ascii=False)}

## バトルログ
{log_text}

以下の見出し（### を使う）で：
### ターン{turn}開始時点の状況（盤面・サイド・手札の推定）
### 考えられた選択肢（2〜3案。手順、メリット、リスク、相手の返し）
### 最善と思われる手とその理由
### 同じような局面で使える原則
"""


# ---------------------------------------------------------------------------
# 保存（ローカルJSON）
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).parent / "data"
STORE_PATH = DATA_DIR / "store.json"


def default_store() -> dict:
    return {
        "settings": {"player_name": ""},
        "decks": {},  # name -> text
        "regulation": DEFAULT_REGULATION,
        "meta_notes": DEFAULT_META_NOTES,
        "meta_updated_at": "2026-08-31",
        "analyses": [],  # 新しい順
    }


def load_store() -> dict:
    base = default_store()
    if STORE_PATH.exists():
        try:
            data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
            base.update(data)
            if not base.get("meta_notes"):
                base["meta_notes"] = DEFAULT_META_NOTES
        except Exception:  # noqa: BLE001
            pass
    return base


def save_store(store: dict) -> None:
    try:
        DATA_DIR.mkdir(exist_ok=True)
        STORE_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001  クラウドで書き込めなくてもアプリは止めない
        pass


def meta_age_days(store: dict) -> Optional[int]:
    try:
        d = datetime.strptime(store.get("meta_updated_at", "")[:10], "%Y-%m-%d")
        return (datetime.now() - d).days
    except Exception:  # noqa: BLE001
        return None


def new_analysis_record(deck_name: str, raw_log: str, extra_notes: str, analysis: dict, model: str) -> dict:
    return {
        "id": uuid.uuid4().hex[:8],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "deck_name": deck_name,
        "raw_log": raw_log,
        "extra_notes": extra_notes,
        "model": model,
        "analysis": analysis,
    }
