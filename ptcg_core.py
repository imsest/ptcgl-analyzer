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
from typing import Optional

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


SYSTEM_PROMPT = """あなたはポケモンカードゲーム（PTCGL / スタンダードレギュレーション）のトッププレイヤー兼コーチです。
将棋の解説者のように、各ターン終了時点の形勢を自分（ユーザー）視点で評価し、悪手と最善手を指摘します。

評価の観点:
- サイドの取り合い（残り枚数、次に何枚取れるか／取られるか、2-2-2 などのプライズマップ）
- 盤面（育っているアタッカー、ベンチの耐久、ex/V の数）
- リソース（手札、山札残り、エネルギー、サポート・スタジアムの残り）
- テンポ（次ターンに攻撃できるか、相手の返しの強さ）

ルール:
- 回答はすべて日本語。カード名はログに書かれた表記のまま使ってよい。
- 相手の手札など見えない情報は断定せず、「〜の可能性が高い」のように確率で語る。確度も示す。
- 「良い手」はログから実行可能だったと判断できる範囲で提案する（手札に無かったカードを前提にしない）。
  不確かな場合はその前提を明示する。
- 形勢が +1以上 から -1以下 に落ちた、または2段階以上悪化した場面は必ず swing_points に入れる。
- ターン評価はログの全ターンについて1件ずつ出す。
"""


def build_analysis_prompt(
    log_text: str,
    my_name: str,
    deck_text: str,
    meta_notes: str,
    extra_notes: str,
) -> str:
    parts = [
        f"## 自分のプレイヤー名\n{my_name or '（未設定：ログから推測して）'}",
        f"## 自分のデッキリスト\n{deck_text or '（未登録）'}",
        f"## 現在の環境メモ\n{meta_notes or '（なし）'}",
        f"## ユーザーからの補足（手札の状況など）\n{extra_notes or '（なし）'}",
        f"## バトルログ\n{log_text}",
        "上のバトルログを解析し、指定のJSON形式で出力してください。",
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
# Gemini 呼び出し
# ---------------------------------------------------------------------------
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


def _wrap_error(e: Exception) -> AIError:
    msg = str(e)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        return AIError("無料枠の利用上限に達しました。1分ほど待つか、明日もう一度試してください。（429 RESOURCE_EXHAUSTED）")
    if "API key" in msg or "API_KEY" in msg or "401" in msg or "403" in msg:
        return AIError("APIキーが正しくないようです。設定を確認してください。")
    if "404" in msg or "not found" in msg.lower():
        return AIError("モデル名が見つかりません。サイドバーでモデルを変更してください。")
    return AIError(f"AIの呼び出しでエラーが発生しました: {msg}")


def analyze_game(api_key: str, model: str, prompt: str) -> dict:
    from google.genai import types

    try:
        resp = _client(api_key).models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=GameAnalysis,
                temperature=0.3,
            ),
        )
    except Exception as e:  # noqa: BLE001
        raise _wrap_error(e) from e

    parsed = getattr(resp, "parsed", None)
    if isinstance(parsed, GameAnalysis):
        return parsed.model_dump()
    try:
        return GameAnalysis.model_validate_json(resp.text).model_dump()
    except Exception as e:  # noqa: BLE001
        raise AIError("AIの返答を読み取れませんでした。もう一度試してください。") from e


def ask_text(api_key: str, model: str, prompt: str, use_search: bool = False) -> str:
    """自由形式（Markdown）の回答を得る。use_search=True で Google 検索を併用。"""
    from google.genai import types

    config_kwargs = dict(system_instruction=SYSTEM_PROMPT, temperature=0.5)
    if use_search:
        config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    try:
        resp = _client(api_key).models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )
    except Exception as e:  # noqa: BLE001
        raise _wrap_error(e) from e
    return resp.text or "（回答が空でした）"


def deck_guide_prompt(deck_text: str, meta_notes: str, focus: str) -> str:
    return f"""次のデッキの戦い方を解説してください。

## デッキリスト
{deck_text}

## 環境メモ
{meta_notes or '（なし）'}

## 特に知りたいこと
{focus or '（特になし）'}

以下の見出しで、具体的に（カード名と順番を出して）書いてください。
1. デッキのコンセプトと勝ち筋（どうやってサイド6枚を取るか、プライズマップ）
2. 理想の展開（先攻1ターン目／後攻1ターン目／2ターン目以降）
3. 序盤の優先順位（手札・状況別の判断基準）
4. 中盤〜終盤の動き方（サイドレースの組み立て方）
5. 環境の主要デッキとの相性と立ち回り（わかる範囲で）
6. よくあるミスと注意点
7. 採用枚数の見直し候補（あれば。理由つき）
"""


def meta_advice_prompt(deck_text: str, meta_notes: str) -> str:
    return f"""次の環境メモを踏まえて、自分のデッキへのアドバイスをください。

## 自分のデッキ
{deck_text}

## 環境メモ
{meta_notes or '（なし）'}

以下を日本語で：
1. 今の環境での立ち位置（有利・不利な相手）
2. 不利対面への対策（立ち回り・採用カードの変更案）
3. 構築の調整案（IN / OUT を枚数つきで、理由も）
4. 練習で意識すべきポイント
"""


META_RESEARCH_PROMPT = """Pokémon TCG Live / ポケモンカードのスタンダード環境について、直近1か月の大会結果
（Limitless TCG など）から、上位に多いデッキタイプを調べてください。
各デッキについて「デッキ名 / 主なアタッカー / 戦い方の特徴 / 目安の使用率や入賞数」を
日本語の箇条書きでまとめ、最後に調査日と情報源のURLを書いてください。"""


def deep_dive_prompt(analysis: dict, turn: int, log_text: str, deck_text: str) -> str:
    return f"""以前の解析結果とバトルログをもとに、ターン{turn}の局面を深掘りしてください。

## 自分のデッキ
{deck_text or '（未登録）'}

## 解析結果（JSON）
{json.dumps(analysis, ensure_ascii=False)}

## バトルログ
{log_text}

以下を日本語で：
1. ターン{turn}開始時点の盤面とサイド状況の整理（わかる範囲で）
2. 考えられた選択肢を2〜3個（それぞれの手順、メリット・リスク、相手の返し）
3. 最善と思われる手とその理由
4. 同じような局面で使える一般原則
"""


# ---------------------------------------------------------------------------
# 保存（ローカルJSON）
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).parent / "data"
STORE_PATH = DATA_DIR / "store.json"

DEFAULT_STORE = {
    "settings": {"player_name": ""},
    "decks": {},  # name -> text
    "meta_notes": "",
    "analyses": [],  # 新しい順
}


def load_store() -> dict:
    if STORE_PATH.exists():
        try:
            data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
            return {**json.loads(json.dumps(DEFAULT_STORE)), **data}
        except Exception:  # noqa: BLE001
            pass
    return json.loads(json.dumps(DEFAULT_STORE))


def save_store(store: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    STORE_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def new_analysis_record(deck_name: str, raw_log: str, extra_notes: str, analysis: dict) -> dict:
    return {
        "id": uuid.uuid4().hex[:8],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "deck_name": deck_name,
        "raw_log": raw_log,
        "extra_notes": extra_notes,
        "analysis": analysis,
    }
