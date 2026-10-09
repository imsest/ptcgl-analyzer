"""PTCGL 自分用分析アプリ（Streamlit）

起動: streamlit run app.py
"""
from __future__ import annotations

import json
import os

import altair as alt
import pandas as pd
import streamlit as st

import ptcg_core as core

st.set_page_config(page_title="PTCGL 分析ノート", page_icon="🃏", layout="wide")


# ---------------------------------------------------------------------------
# 設定値（secrets.toml → 環境変数 → 画面入力 の順に探す）
# ---------------------------------------------------------------------------
def secret(name: str, default: str = "") -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # secrets.toml が無い場合
        pass
    return os.environ.get(name, default)


# 簡易パスワード（ネット公開時に他人にAPI枠を使われないように）
APP_PASSWORD = secret("APP_PASSWORD")
if APP_PASSWORD and not st.session_state.get("authed"):
    st.title("🔒 PTCGL 分析ノート")
    pw = st.text_input("パスワード", type="password")
    if st.button("ログイン"):
        if pw == APP_PASSWORD:
            st.session_state.authed = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    st.stop()

if "store" not in st.session_state:
    st.session_state.store = core.load_store()
store = st.session_state.store


def persist():
    core.save_store(store)


# ---------------------------------------------------------------------------
# サイドバー
# ---------------------------------------------------------------------------
MODEL_CHOICES = ["gemini-flash-latest", "gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "その他（手入力）"]

with st.sidebar:
    st.header("⚙️ 設定")
    api_key = secret("GEMINI_API_KEY")
    if not api_key:
        api_key = st.text_input("Gemini APIキー", type="password", help="secrets.toml に書いておけば毎回の入力は不要です")
    else:
        st.caption("✅ APIキー設定済み")

    model_sel = st.selectbox("AIモデル", MODEL_CHOICES, help="429エラーが続く場合は Flash-Lite に切り替えると枠に余裕が出ます")
    model = st.text_input("モデル名", "gemini-3.8-flash") if model_sel.startswith("その他") else model_sel

    name = st.text_input("自分のPTCGLプレイヤー名", store["settings"].get("player_name", ""),
                         help="ログのどちらが自分かを判定するのに使います")
    if name != store["settings"].get("player_name"):
        store["settings"]["player_name"] = name
        persist()

    st.divider()
    st.subheader("💾 バックアップ")
    st.download_button("データを書き出す", json.dumps(store, ensure_ascii=False, indent=2),
                       file_name="ptcgl_backup.json", mime="application/json")
    up = st.file_uploader("データを読み込む", type="json")
    if up is not None and st.button("読み込みを実行"):
        try:
            st.session_state.store = {**core.DEFAULT_STORE, **json.load(up)}
            store = st.session_state.store
            persist()
            st.success("読み込みました")
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"読み込めませんでした: {e}")
    st.caption("クラウド公開版は再起動でデータが消えることがあります。こまめに書き出してください。")


def need_key() -> bool:
    if not api_key:
        st.warning("サイドバーで Gemini APIキーを設定してください。")
        return True
    return False


def deck_selector(key: str, allow_none: bool = True) -> tuple[str, str]:
    names = list(store["decks"].keys())
    options = (["（指定しない）"] if allow_none else []) + names
    if not options:
        st.info("まだデッキが登録されていません。「デッキ」タブで登録してください。")
        return "", ""
    sel = st.selectbox("デッキ", options, key=key)
    if sel == "（指定しない）":
        return "", ""
    return sel, store["decks"].get(sel, "")


SCORE_COLORS = {2: "#1a7f37", 1: "#4caf50", 0: "#8c8c8c", -1: "#e07b39", -2: "#cf222e"}


def render_analysis(rec: dict):
    a = rec["analysis"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("結果", a.get("result", "不明"))
    c2.metric("先攻/後攻", a.get("went_first", "不明"))
    c3.metric("相手デッキ（推定）", a.get("opponent_deck_guess", "不明"))
    c4.metric("相手", a.get("opponent_name", "-"))

    st.markdown("#### 総評")
    st.write(a.get("overall_summary", ""))

    turns = a.get("turns", [])
    if turns:
        df = pd.DataFrame(turns)
        df["形勢"] = df["score"].apply(core.eval_label)
        df["手番"] = df["player"]
        st.markdown("#### 形勢グラフ（上が自分有利）")
        base = alt.Chart(df).encode(
            x=alt.X("turn:O", title="ターン"),
            y=alt.Y("score:Q", title="形勢", scale=alt.Scale(domain=[-2.3, 2.3]),
                    axis=alt.Axis(values=[-2, -1, 0, 1, 2],
                                  labelExpr="datum.value == 2 ? '優勢' : datum.value == 1 ? 'やや優勢' : "
                                            "datum.value == 0 ? '互角' : datum.value == -1 ? 'やや劣勢' : '劣勢'")),
        )
        zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(strokeDash=[4, 4], color="#999").encode(y="y:Q")
        line = base.mark_line(color="#6e7781")
        pts = base.mark_circle(size=140).encode(
            color=alt.Color("手番:N", scale=alt.Scale(domain=["自分", "相手"], range=["#0969da", "#cf222e"])),
            tooltip=["turn", "手番", "形勢", "summary"],
        )
        st.altair_chart(zero + line + pts, use_container_width=True)

    # 転換点（AI指摘 + コード検出）
    ai_swings = {s["turn"]: s for s in a.get("swing_points", [])}
    auto_swings = core.detect_swings(turns)
    st.markdown("#### 🔻 形勢が傾いた場面と、打つべきだった手")
    if not ai_swings and not auto_swings:
        st.success("大きく形勢を損ねた場面は見つかりませんでした。")
    for t in sorted(set(ai_swings) | set(auto_swings)):
        s = ai_swings.get(t)
        with st.container(border=True):
            st.markdown(f"**ターン {t}**" + ("　（グラフ上で急落を検出）" if t in auto_swings and not s else ""))
            if s:
                st.markdown(f"**何が起きたか**：{s['what_happened']}")
                st.markdown(f"**打つべきだった手**：{s['better_play']}")
                st.markdown(f"**理由**：{s['why']}")
                if s.get("alternative_line"):
                    st.markdown("**代替手順**")
                    for i, step in enumerate(s["alternative_line"], 1):
                        st.markdown(f"{i}. {step}")
                st.caption(f"確度：{s.get('confidence', '-')}")
            dd_key = f"dd_{rec['id']}_{t}"
            if st.button("この局面を深掘りする", key=f"btn_{dd_key}"):
                if not need_key():
                    with st.spinner("深掘り中…"):
                        try:
                            deck_text = store["decks"].get(rec.get("deck_name", ""), "")
                            rec.setdefault("deep_dives", {})[str(t)] = core.ask_text(
                                api_key, model, core.deep_dive_prompt(a, t, rec["raw_log"], deck_text))
                            persist()
                        except core.AIError as e:
                            st.error(str(e))
            if rec.get("deep_dives", {}).get(str(t)):
                st.markdown(rec["deep_dives"][str(t)])

    st.markdown("#### ターンごとの評価")
    for t in turns:
        icon = "🟦" if t["player"] == "自分" else "🟥"
        label = core.eval_label(t["score"])
        with st.expander(f"{icon} ターン{t['turn']}（{t['player']}）　形勢：{label}　— {t['summary']}"):
            st.markdown(f"**評価の根拠**：{t['reason']}")
            if t.get("key_actions"):
                st.markdown("**主な行動**：" + " / ".join(t["key_actions"]))
            if t.get("better_play"):
                st.info(f"💡 より良い手：{t['better_play']}")

    if a.get("lessons"):
        st.markdown("#### 📝 次に活かす教訓")
        for l in a["lessons"]:
            st.markdown(f"- {l}")


# ---------------------------------------------------------------------------
# タブ
# ---------------------------------------------------------------------------
st.title("🃏 PTCGL 分析ノート")
tab_log, tab_hist, tab_deck, tab_meta = st.tabs(["⚔️ ログ解析", "📚 履歴", "🗂 デッキ", "🌐 環境"])

# --- ログ解析 ---------------------------------------------------------------
with tab_log:
    st.caption("PTCGL の対戦終了画面 →「バトルログ」→ 全選択してコピー → 下に貼り付け")
    deck_name, deck_text = deck_selector("log_deck")
    raw_log = st.text_area("バトルログ", height=260, placeholder="Setup\n...\nTurn # 1 - YourName's Turn\n...")
    extra = st.text_area("補足（任意）", height=80,
                         placeholder="例：ターン5の時点で手札にボスの指令があった／サイド落ちが〇〇だった など。精度が上がります")

    if raw_log.strip():
        parsed = core.parse_log(raw_log)
        if parsed.ok:
            st.caption(f"読み取り：{len(parsed.turns)}ターン / プレイヤー：{'・'.join(parsed.players)}")
            if store["settings"].get("player_name") and store["settings"]["player_name"] not in parsed.players:
                st.warning("設定したプレイヤー名がログに見つかりません。サイドバーの名前を確認してください。")
        else:
            st.caption("ターンの区切りを自動判定できませんでしたが、そのままAIに渡して解析できます。")

    if st.button("🔍 解析する", type="primary", disabled=not raw_log.strip()):
        if not need_key():
            parsed = core.parse_log(raw_log)
            prompt = core.build_analysis_prompt(
                core.format_log_for_ai(parsed, raw_log),
                store["settings"].get("player_name", ""),
                deck_text, store.get("meta_notes", ""), extra,
            )
            with st.spinner("AIが1ターンずつ検討中…（30秒〜1分ほど）"):
                try:
                    analysis = core.analyze_game(api_key, model, prompt)
                    rec = core.new_analysis_record(deck_name, raw_log, extra, analysis)
                    store["analyses"].insert(0, rec)
                    persist()
                    st.session_state.current_id = rec["id"]
                except core.AIError as e:
                    st.error(str(e))

    cur = next((r for r in store["analyses"] if r["id"] == st.session_state.get("current_id")), None)
    if cur:
        st.divider()
        render_analysis(cur)

# --- 履歴 ------------------------------------------------------------------
with tab_hist:
    recs = store["analyses"]
    if not recs:
        st.info("まだ解析した試合がありません。")
    else:
        rows = [{
            "日時": r["created_at"],
            "デッキ": r.get("deck_name") or "-",
            "相手デッキ": r["analysis"].get("opponent_deck_guess", "-"),
            "結果": r["analysis"].get("result", "-"),
        } for r in recs]
        hdf = pd.DataFrame(rows)
        wins = (hdf["結果"] == "勝ち").sum()
        losses = (hdf["結果"] == "負け").sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("解析した試合", len(hdf))
        c2.metric("勝敗", f"{wins}勝 {losses}敗")
        c3.metric("勝率", f"{wins / max(1, wins + losses):.0%}")

        st.markdown("##### 相手デッキ別の成績")
        mu = hdf[hdf["結果"].isin(["勝ち", "負け"])].pivot_table(
            index="相手デッキ", columns="結果", aggfunc="size", fill_value=0)
        st.dataframe(mu, use_container_width=True)

        st.markdown("##### 試合一覧")
        labels = [f"{r['created_at']}｜{r['analysis'].get('result', '-')}｜vs {r['analysis'].get('opponent_deck_guess', '-')}"
                  for r in recs]
        idx = st.selectbox("表示する試合", range(len(recs)), format_func=lambda i: labels[i])
        col_a, col_b = st.columns([1, 5])
        if col_a.button("🗑 削除", key="del_rec"):
            recs.pop(idx)
            persist()
            st.rerun()
        render_analysis(recs[idx])

# --- デッキ ----------------------------------------------------------------
with tab_deck:
    st.caption("PTCGL のデッキ編集画面で「エクスポート（コピー）」したテキストをそのまま貼り付けます")
    names = list(store["decks"].keys())
    mode = st.radio("操作", ["新規登録", "既存デッキを編集"] if names else ["新規登録"], horizontal=True)
    if mode == "新規登録":
        dname = st.text_input("デッキ名", placeholder="例：リザードンex")
        dtext = st.text_area("デッキリスト", height=300, key="new_deck_text")
    else:
        dname = st.selectbox("デッキ", names)
        dtext = st.text_area("デッキリスト", store["decks"][dname], height=300, key=f"edit_{dname}")

    if dtext.strip():
        d = core.parse_deck(dtext)
        cnt = d["counts"]
        st.caption(f"ポケモン {cnt['pokemon']} / トレーナーズ {cnt['trainer']} / エネルギー {cnt['energy']} ／ 合計 {d['total']}枚")
        if d["total"] != 60:
            st.warning("合計が60枚ではありません。貼り付け漏れがないか確認してください。")

    c1, c2 = st.columns(2)
    if c1.button("💾 保存", disabled=not (dname and dtext.strip())):
        store["decks"][dname] = dtext
        persist()
        st.success(f"「{dname}」を保存しました")
    if mode != "新規登録" and c2.button("🗑 このデッキを削除"):
        store["decks"].pop(dname, None)
        persist()
        st.rerun()

    st.divider()
    st.subheader("📖 このデッキの戦い方・展開方法")
    g_name, g_text = deck_selector("guide_deck", allow_none=False)
    focus = st.text_input("特に知りたいこと（任意）", placeholder="例：後攻1ターン目の動き方、〇〇デッキ対面の立ち回り")
    if st.button("戦い方を解説してもらう", disabled=not g_text):
        if not need_key():
            with st.spinner("解説を作成中…"):
                try:
                    store.setdefault("guides", {})[g_name] = core.ask_text(
                        api_key, model, core.deck_guide_prompt(g_text, store.get("meta_notes", ""), focus))
                    persist()
                except core.AIError as e:
                    st.error(str(e))
    if g_name and store.get("guides", {}).get(g_name):
        st.markdown(store["guides"][g_name])

# --- 環境 ------------------------------------------------------------------
with tab_meta:
    st.caption("大会結果（Limitless TCG など）を見て、流行デッキや気づきをメモしておくと、全ての解析・アドバイスに反映されます")
    if st.button("🔎 AIに最新の環境を調べてもらう（Google検索を使用）"):
        if not need_key():
            with st.spinner("調査中…"):
                try:
                    found = core.ask_text(api_key, model, core.META_RESEARCH_PROMPT, use_search=True)
                    st.session_state.meta_draft = found
                except core.AIError as e:
                    st.error(str(e) + "（検索機能が使えない場合は、手動でメモを書いてください）")
    if st.session_state.get("meta_draft"):
        st.markdown(st.session_state.meta_draft)
        if st.button("↓ この内容を環境メモに追記"):
            store["meta_notes"] = (store.get("meta_notes", "") + "\n\n" + st.session_state.meta_draft).strip()
            st.session_state.meta_draft = ""
            persist()
            st.rerun()

    notes = st.text_area("環境メモ", store.get("meta_notes", ""), height=260)
    if st.button("💾 環境メモを保存"):
        store["meta_notes"] = notes
        persist()
        st.success("保存しました")

    st.divider()
    st.subheader("🧭 環境を踏まえたデッキアドバイス")
    m_name, m_text = deck_selector("meta_deck", allow_none=False)
    if st.button("アドバイスをもらう", disabled=not m_text):
        if not need_key():
            with st.spinner("考え中…"):
                try:
                    store.setdefault("meta_advice", {})[m_name] = core.ask_text(
                        api_key, model, core.meta_advice_prompt(m_text, store.get("meta_notes", "")))
                    persist()
                except core.AIError as e:
                    st.error(str(e))
    if m_name and store.get("meta_advice", {}).get(m_name):
        st.markdown(store["meta_advice"][m_name])
