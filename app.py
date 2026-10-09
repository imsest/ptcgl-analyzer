"""PTCGL 対局検討（Streamlit）— スマホ表示を最優先にした1カラム構成

起動: streamlit run app.py
"""
from __future__ import annotations

import html
import json
import os

import altair as alt
import pandas as pd
import streamlit as st

import ptcg_core as core

_ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "icon.png")
st.set_page_config(page_title="PTCGL 対局検討", page_icon=_ICON if os.path.exists(_ICON) else "🃏", layout="centered",
                   initial_sidebar_state="collapsed")

# ---------------------------------------------------------------------------
# デザイン（スマホ幅 375〜430px を基準に、PCでは幅 680px の1カラム）
# ---------------------------------------------------------------------------
C = {
    "bg": "#141B2E", "surface": "#1D2742", "line": "#2C3858", "grid": "#232E4B", "ink": "#E9EDF6",
    "muted": "#93A0BD", "me": "#5AA9FF", "opp": "#FF7A66", "gold": "#F2C14E",
}

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@400;500;700;900&family=Barlow+Condensed:wght@500;700&display=swap');

html, body, [class*="css"], .stMarkdown, button, input, textarea, select {{
  font-family: 'Zen Kaku Gothic New', 'Hiragino Sans', sans-serif !important;
}}
.stApp {{ background: {C['bg']}; }}
.block-container {{ max-width: 680px; padding: 1rem 1rem calc(4rem + env(safe-area-inset-bottom, 0px)); }}
header[data-testid="stHeader"] {{ display: none; }}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], #MainMenu, footer {{ display: none; }}
p, li {{ line-height: 1.8; }}

/* iPhone は 16px 未満の入力欄をタップすると画面を拡大するので 16px に固定 */
.stTextArea textarea, .stTextInput input, .stSelectbox div[data-baseweb="select"] {{ font-size: 16px !important; }}
.stTextArea textarea, .stTextInput input {{ background: {C['surface']} !important; border-radius: 12px !important; }}
.stTextArea textarea {{ line-height: 1.55; }}
label p {{ font-size: .9rem !important; color: {C['muted']} !important; }}

/* 見出し */
.stMarkdown h3 {{ font-size: 1.02rem; font-weight: 700; margin: 1.6rem 0 .6rem; padding: 0 0 0 .65rem;
  border-left: 3px solid {C['gold']}; }}

/* タブ：5つを画面幅いっぱいに等分 */
.stTabs [data-baseweb="tab-list"] {{ gap: 0; border-bottom: 1px solid {C['line']}; }}
.stTabs [data-baseweb="tab"] {{ flex: 1 1 0; justify-content: center; height: 3rem; padding: 0 .2rem;
  color: {C['muted']}; font-weight: 700; }}
.stTabs [data-baseweb="tab"] p {{ font-size: .95rem; }}
.stTabs [aria-selected="true"] {{ color: {C['ink']}; }}
.stTabs [data-baseweb="tab-highlight"] {{ background: {C['gold']}; }}
.stTabs [data-baseweb="tab-border"] {{ display: none; }}

/* ボタン：指で押しやすい高さ */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
  min-height: 3rem; border-radius: 14px; font-weight: 700; font-size: 1rem;
  border: 1px solid {C['line']}; background: transparent; color: {C['ink']}; }}
.stButton > button:hover {{ border-color: {C['gold']}; color: {C['gold']}; }}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
  background: {C['gold']}; color: #1A1608; border: none; }}
.stButton > button[kind="primary"]:hover {{ background: #F7D277; color: #1A1608; }}
button:focus-visible, summary:focus-visible {{ outline: 2px solid {C['gold']} !important; outline-offset: 2px; }}

/* 折りたたみ */
[data-testid="stExpander"] details {{ border-radius: 14px; border-color: {C['line']}; }}
[data-testid="stExpander"] summary p {{ font-weight: 700; }}

/* 自作パーツ */
.brand {{ display: flex; justify-content: space-between; align-items: baseline; gap: .5rem; margin: .2rem 0 .4rem; }}
.brand h1 {{ font-size: 1.3rem; font-weight: 900; margin: 0; padding: 0; }}
.brand span {{ color: {C['muted']}; font-size: .75rem; white-space: nowrap; }}
.hint {{ color: {C['muted']}; font-size: .85rem; margin: .2rem 0 .6rem; line-height: 1.6; }}
.notice {{ border: 1px solid {C['line']}; border-radius: 14px; padding: .8rem 1rem; color: {C['muted']};
  font-size: .9rem; margin: .4rem 0 .8rem; line-height: 1.65; }}
.notice b {{ color: {C['ink']}; }}
.empty {{ color: {C['muted']}; padding: 1.6rem 0; line-height: 1.7; }}

.verdict {{ padding: 1.1rem 0 1rem; border-bottom: 1px solid {C['line']}; }}
.verdict .top {{ display: flex; align-items: center; gap: 1rem; }}
.verdict .result {{ font-size: 2.6rem; font-weight: 900; line-height: 1; }}
.verdict .facts {{ display: grid; grid-template-columns: 1fr 1fr; gap: .25rem 1rem; font-size: .85rem;
  color: {C['muted']}; flex: 1; min-width: 0; }}
.verdict .facts b {{ display: block; color: {C['ink']}; font-size: .95rem; overflow-wrap: anywhere; line-height: 1.35; }}
.verdict p {{ margin: .9rem 0 0; font-size: .95rem; }}

.meter {{ margin: 1.1rem 0 .2rem; }}
.meter .now {{ font-size: .9rem; margin-bottom: .4rem; }}
.meter .now b {{ font-family: 'Barlow Condensed', sans-serif; font-size: 1.4rem; margin: 0 .3rem 0 .4rem; }}
.meter .bar {{ position: relative; height: 12px; border-radius: 999px;
  background: linear-gradient(90deg, {C['opp']} 0 50%, {C['me']} 50% 100%); }}
.meter .fill {{ position: absolute; top: 0; bottom: 0; background: {C['bg']}; opacity: .78; }}
.meter .scale {{ display: flex; justify-content: space-between; color: {C['muted']}; font-size: .72rem; margin-top: .3rem; }}

.swing {{ border: 1px solid {C['gold']}; border-radius: 16px; padding: .95rem 1rem 1rem; margin: .7rem 0 .4rem;
  background: rgba(242,193,78,.05); }}
.swing .head {{ display: flex; align-items: center; gap: .6rem; }}
.swing .t {{ font-family: 'Barlow Condensed', sans-serif; font-size: 1.7rem; font-weight: 700; color: {C['gold']}; line-height: 1; }}
.swing .conf {{ margin-left: auto; color: {C['muted']}; font-size: .75rem; border: 1px solid {C['line']};
  border-radius: 999px; padding: .1rem .6rem; white-space: nowrap; }}
.swing .what {{ margin: .5rem 0 0; font-size: .95rem; }}
.swing dt {{ color: {C['muted']}; font-size: .78rem; margin-top: .7rem; }}
.swing dd {{ margin: .1rem 0 0; font-size: .95rem; line-height: 1.7; }}
.swing dd.play {{ font-weight: 700; font-size: 1.02rem; }}
.swing ol {{ margin: .1rem 0 0; padding-left: 1.2rem; }}

.record {{ border-top: 1px solid {C['line']}; }}
.record details {{ border-bottom: 1px solid {C['line']}; }}
.record summary {{ list-style: none; cursor: pointer; padding: .75rem .1rem; -webkit-tap-highlight-color: transparent; }}
.record summary::-webkit-details-marker {{ display: none; }}
.record .row {{ display: flex; align-items: center; gap: .5rem; }}
.record .n {{ font-family: 'Barlow Condensed', sans-serif; font-size: 1.3rem; font-weight: 700; color: {C['muted']};
  min-width: 2.2rem; }}
.record .who {{ font-size: .75rem; font-weight: 700; padding: .1rem .55rem; border-radius: 999px; }}
.record .who.me {{ color: {C['me']}; border: 1px solid {C['me']}; }}
.record .who.opp {{ color: {C['opp']}; border: 1px solid {C['opp']}; }}
.record .ev {{ font-size: .78rem; font-weight: 700; padding: .12rem .55rem; border-radius: 6px; }}
.record .flag {{ color: {C['gold']}; font-size: .78rem; font-weight: 700; margin-left: auto; }}
.record .chev {{ color: {C['muted']}; font-size: .8rem; margin-left: auto; transition: transform .15s; }}
.record .flag + .chev {{ margin-left: .4rem; }}
.record details[open] .chev {{ transform: rotate(180deg); }}
.record .sum {{ margin: .3rem 0 0 2.7rem; font-size: .93rem; line-height: 1.6; }}
.record .prize {{ display: block; color: {C['muted']}; font-size: .75rem; margin-top: .15rem; }}
.record .body {{ margin: 0 0 .9rem 2.7rem; font-size: .9rem; }}
.record .body p {{ margin: .45rem 0 0; line-height: 1.7; }}
.record .k {{ display: block; color: {C['muted']}; font-size: .75rem; }}
.record .better {{ border-left: 3px solid {C['gold']}; padding-left: .65rem; }}
@media (prefers-reduced-motion: reduce) {{ .record .chev {{ transition: none; }} }}

.lessons {{ margin: 0; padding-left: 1.2rem; }}
.lessons li {{ margin-bottom: .35rem; }}
.answer-meta {{ color: {C['muted']}; font-size: .78rem; margin: .5rem 0 .2rem; line-height: 1.6; }}
.sources {{ font-size: .82rem; color: {C['muted']}; }}
.sources a {{ color: {C['me']}; overflow-wrap: anywhere; }}
.deckcount {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: .3rem; margin: .1rem 0 .7rem; }}
.deckcount div {{ border: 1px solid {C['line']}; border-radius: 12px; padding: .4rem .2rem; text-align: center;
  color: {C['muted']}; font-size: .72rem; }}
.deckcount b {{ display: block; font-family: 'Barlow Condensed', sans-serif; font-size: 1.35rem; color: {C['ink']}; line-height: 1.1; }}
.deckcount .ng b {{ color: {C['opp']}; }} .deckcount .ok b {{ color: {C['me']}; }}
.stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: .5rem; margin: .8rem 0 .4rem; }}
.stats div {{ border: 1px solid {C['line']}; border-radius: 14px; padding: .6rem .4rem; text-align: center;
  color: {C['muted']}; font-size: .75rem; }}
.stats b {{ display: block; font-family: 'Barlow Condensed', sans-serif; font-size: 1.7rem; color: {C['ink']}; line-height: 1.1; }}
.mu {{ border-top: 1px solid {C['line']}; }}
.mu div {{ display: flex; justify-content: space-between; gap: .8rem; padding: .6rem .1rem; border-bottom: 1px solid {C['line']};
  font-size: .9rem; }}
.mu span:first-child {{ min-width: 0; overflow-wrap: anywhere; }}
.mu span:last-child {{ white-space: nowrap; color: {C['muted']}; }}
.mu b {{ font-family: 'Barlow Condensed', sans-serif; font-size: 1.05rem; color: {C['ink']}; margin-left: .3rem; }}
</style>
""", unsafe_allow_html=True)

E = html.escape


def register_home_icon():
    """iPhone の「ホーム画面に追加」で使うアイコンを、アプリの外枠のページに登録する。

    static/apple-touch-icon.png を Streamlit の静的配信（/app/static/...）で公開し、その URL を
    外枠の <head> に <link rel="apple-touch-icon"> として追加する。
    """
    import streamlit.components.v1 as components
    components.html("""<script>
(function () {
  function add(doc, href) {
    if (!doc || !doc.head || doc.querySelector('link[data-ptcgl-icon]')) return;
    var l = doc.createElement('link'); l.rel = 'apple-touch-icon'; l.sizes = '180x180'; l.href = href;
    l.setAttribute('data-ptcgl-icon', '1'); doc.head.appendChild(l);
    var t = doc.createElement('meta'); t.name = 'apple-mobile-web-app-title'; t.content = 'PTCGL検討';
    doc.head.appendChild(t);
  }
  try {
    var app = window.parent;
    var href = new URL('app/static/apple-touch-icon.png', app.location.href).href;
    add(app.document, href);
    try { if (window.top !== app) add(window.top.document, href); } catch (e) {}
  } catch (e) {}
})();
</script>""", height=0)


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


def brand(sub: str = ""):
    st.markdown(f'<div class="brand"><h1>PTCGL 対局検討</h1><span>{E(sub)}</span></div>', unsafe_allow_html=True)


register_home_icon()  # ログイン画面でもアイコンが登録されるよう、最初に呼ぶ

APP_PASSWORD = secret("APP_PASSWORD")
if APP_PASSWORD and not st.session_state.get("authed"):
    brand()
    with st.form("login"):
        pw = st.text_input("パスワード", type="password")
        if st.form_submit_button("ログイン", type="primary", width="stretch"):
            if pw == APP_PASSWORD:
                st.session_state.authed = True
                st.rerun()
            else:
                st.error("パスワードが違います。Secrets の APP_PASSWORD と同じものを入力してください。")
    st.stop()

if "store" not in st.session_state:
    st.session_state.store = core.load_store()
store = st.session_state.store
if not store["settings"].get("player_name") and secret("PLAYER_NAME"):
    store["settings"]["player_name"] = secret("PLAYER_NAME")

MODEL_CHOICES = ["gemini-flash-latest", "gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]
SECRET_KEY = secret("GEMINI_API_KEY")


def api_key() -> str:
    return SECRET_KEY or st.session_state.get("api_key_input", "")


def model() -> str:
    return st.session_state.get("model_sel", MODEL_CHOICES[0])


def persist():
    core.save_store(store)


def need_key() -> bool:
    if not api_key():
        st.warning("APIキーが未設定です。「設定」タブで Gemini APIキーを入力してください。")
        return True
    return False


def deck_options() -> list[str]:
    return list(store["decks"].keys())


def run_ai(label: str, fn):
    """進行状況（再試行・モデル切替）を表示しながらAIを呼ぶ。"""
    with st.status(label, expanded=False) as s:
        try:
            result = fn(lambda m: s.write(m))
            s.update(label="完了", state="complete")
            return result
        except core.AIError as e:
            s.update(label="うまくいきませんでした", state="error")
            st.error(str(e))
            return None


def stream_answer(prompt: str, use_search: bool, label: str):
    """回答を書けたところから順に表示する。完了したら回答(dict)を返す。"""
    res: dict = {}
    note = st.empty()
    note.caption(label)
    try:
        st.write_stream(core.stream_text(api_key(), model(), prompt, store["regulation"], res,
                                         use_search=use_search, notify=lambda m: note.caption(m)))
    except core.AIError as e:
        note.empty()
        st.error(str(e))
        return None
    note.empty()
    return res if res.get("text") else None


def meta_is_fresh() -> bool:
    """環境メモが7日以内に更新されていれば、毎回の検索を省いて速く答える。"""
    a = core.meta_age_days(store)
    return a is not None and a <= 7


def show_answer(ans):
    if not ans:
        return
    if not isinstance(ans, dict):
        ans = {"text": str(ans), "model": "-", "at": "-"}
    st.markdown(ans["text"])
    meta = f"{ans['at']} 作成・{ans['model']}"
    if "searched" in ans:
        meta += "・Google検索で最新情報を確認済み" if ans["searched"] else "・検索なし（保存した環境メモで回答）"
    st.markdown(f'<div class="answer-meta">{E(meta)}</div>', unsafe_allow_html=True)
    if ans.get("sources"):
        links = "".join(f'<li><a href="{E(s["url"])}" target="_blank">{E(s["title"])}</a></li>' for s in ans["sources"][:8])
        st.markdown(f'<details class="sources"><summary>参照したページ</summary><ul>{links}</ul></details>',
                    unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 解析結果の表示
# ---------------------------------------------------------------------------
EV_STYLE = {
    2: (C["me"], "rgba(90,169,255,.18)"), 1: (C["me"], "rgba(90,169,255,.08)"), 0: (C["muted"], "rgba(147,160,189,.12)"),
    -1: (C["opp"], "rgba(255,122,102,.08)"), -2: (C["opp"], "rgba(255,122,102,.18)"),
}


def meter_html(score: int) -> str:
    s = max(-2, min(2, int(score)))
    pos = (s + 2) / 4 * 100
    # 中央(互角)から現在値までだけを明るく残し、残りを暗くして針のように見せる
    if s > 0:
        fill = f'<div class="fill" style="left:0;width:50%"></div><div class="fill" style="left:{pos}%;right:0"></div>'
    elif s < 0:
        fill = f'<div class="fill" style="left:0;width:{pos}%"></div><div class="fill" style="left:50%;right:0"></div>'
    else:
        fill = '<div class="fill" style="left:0;width:49%"></div><div class="fill" style="left:51%;right:0"></div>'
    return f"""<div class="meter">
  <div class="now">最終盤面<b style="color:{EV_STYLE[s][0]}">{s:+d}</b>{E(core.eval_label(s))}</div>
  <div class="bar">{fill}</div>
  <div class="scale"><span>相手優勢</span><span>互角</span><span>自分優勢</span></div>
</div>"""


def eval_chart(turns: list[dict], swings: set[int]):
    df = pd.DataFrame(turns)
    df["score"] = df["score"].clip(-2, 2)
    df["pos"] = df["score"].clip(lower=0)
    df["neg"] = df["score"].clip(upper=0)
    df["形勢"] = df["score"].apply(core.eval_label)
    df["手番"] = df["player"]
    x = alt.X("turn:Q", title=None, axis=alt.Axis(tickMinStep=1, format="d", labelFontSize=11),
              scale=alt.Scale(domain=[df["turn"].min(), df["turn"].max()], nice=False))
    ys = alt.Scale(domain=[-2.3, 2.3])
    yaxis = alt.Axis(values=[-2, 0, 2], title=None, labelFontSize=11, labelPadding=4,
                     labelExpr="datum.value == 2 ? '優勢' : datum.value == 0 ? '互角' : '劣勢'")
    base = alt.Chart(df)
    layers = [
        base.mark_area(color=C["me"], opacity=.28, interpolate="monotone").encode(x=x, y=alt.Y("pos:Q", scale=ys, axis=yaxis), y2=alt.datum(0)),
        base.mark_area(color=C["opp"], opacity=.28, interpolate="monotone").encode(x=x, y=alt.Y("neg:Q", scale=ys), y2=alt.datum(0)),
        alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=C["line"]).encode(y="y:Q"),
    ]
    if swings:
        layers.append(alt.Chart(pd.DataFrame({"turn": sorted(swings)})).mark_rule(color=C["gold"], strokeDash=[4, 4]).encode(x="turn:Q"))
    layers += [
        base.mark_line(color=C["ink"], strokeWidth=1.6, interpolate="monotone").encode(x=x, y=alt.Y("score:Q", scale=ys)),
        base.mark_circle(size=70, opacity=1).encode(
            x=x, y=alt.Y("score:Q", scale=ys),
            color=alt.Color("手番:N", scale=alt.Scale(domain=["自分", "相手"], range=[C["me"], C["opp"]]), legend=None),
            tooltip=[alt.Tooltip("turn:Q", title="ターン"), "手番", "形勢", alt.Tooltip("summary:N", title="内容")]),
    ]
    chart = alt.layer(*layers).properties(height=190).configure(background="transparent", padding={"left": 0, "right": 6, "top": 6, "bottom": 0}).configure_axis(
        labelColor=C["muted"], gridColor=C["grid"], domainColor=C["line"], tickColor=C["line"], labelFont="Zen Kaku Gothic New",
    ).configure_view(strokeWidth=0)
    st.altair_chart(chart, width="stretch")
    st.markdown(f'<p class="hint"><span style="color:{C["me"]}">●</span> 自分の番　<span style="color:{C["opp"]}">●</span> 相手の番　'
                f'<span style="color:{C["gold"]}">┆</span> 形勢が傾いたターン</p>', unsafe_allow_html=True)


def render_analysis(rec: dict):
    a = rec["analysis"]
    turns = sorted(a.get("turns", []), key=lambda t: t["turn"])
    result = a.get("result", "不明")
    rcolor = C["me"] if result == "勝ち" else C["opp"] if result == "負け" else C["muted"]
    st.markdown(f"""<div class="verdict">
  <div class="top"><div class="result" style="color:{rcolor}">{E(result)}</div>
    <div class="facts">
      <span>相手デッキ<b>{E(a.get('opponent_deck_guess', '不明'))}</b></span>
      <span>相手<b>{E(a.get('opponent_name', '-'))}</b></span>
      <span>手番<b>{E(a.get('went_first', '不明'))}</b></span>
      <span>ターン数<b>{len(turns)}</b></span>
    </div></div>
  <p>{E(a.get('overall_summary', ''))}</p>
</div>""", unsafe_allow_html=True)

    if rec.get("model") == "自動評価":
        st.markdown('<div class="notice"><b>AIの検討を取得できなかったため、サイド差だけで形勢を表示しています。</b>'
                    '少し時間をおいて「別の対局を検討する」から同じログで検討し直すと、AIの解説つきになります。</div>',
                    unsafe_allow_html=True)
    if not turns:
        return
    ai_swings = {int(s["turn"]): s for s in a.get("swing_points", [])}
    swings = set(ai_swings) | set(core.detect_swings(turns))

    st.markdown(meter_html(turns[-1]["score"]), unsafe_allow_html=True)
    eval_chart(turns, swings)
    best = max(turns, key=lambda t: t["score"])
    if best["score"] >= 1 and turns[-1]["score"] <= -1:
        st.markdown(f'<div class="notice">ターン{best["turn"]}では<b>{E(core.eval_label(best["score"]))}</b>でしたが、'
                    f'そこから逆転されています。下の「形勢が傾いた場面」を確認してください。</div>', unsafe_allow_html=True)

    st.markdown("### 形勢が傾いた場面")
    if not swings:
        st.markdown('<div class="empty">大きく形勢を損ねた場面はありませんでした。</div>', unsafe_allow_html=True)
    for t in sorted(swings):
        s = ai_swings.get(t)
        if s:
            steps = "".join(f"<li>{E(x)}</li>" for x in s.get("alternative_line", []))
            st.markdown(f"""<div class="swing">
  <div class="head"><span class="t">T{t}</span><span class="conf">確度 {E(s.get('confidence', '-'))}</span></div>
  <p class="what">{E(s['what_happened'])}</p>
  <dl><dt>打つべきだった手</dt><dd class="play">{E(s['better_play'])}</dd>
    <dt>理由</dt><dd>{E(s['why'])}</dd>
    {'<dt>手順</dt><dd><ol>' + steps + '</ol></dd>' if steps else ''}</dl>
</div>""", unsafe_allow_html=True)
        else:
            row = next((x for x in turns if x["turn"] == t), {})
            st.markdown(f"""<div class="swing"><div class="head"><span class="t">T{t}</span></div>
  <p class="what">グラフ上で形勢が大きく下がったターンです。{E(row.get('summary', ''))}</p>
  <dl><dt>より良い手</dt><dd class="play">{E(row.get('better_play') or '下のボタンで詳しく検討できます')}</dd></dl></div>""",
                        unsafe_allow_html=True)
        if st.button(f"T{t} を深掘りする", key=f"dd_{rec['id']}_{t}", width="stretch"):
            if not need_key():
                deck_text = store["decks"].get(rec.get("deck_name", ""), "")
                ans = stream_answer(core.deep_dive_prompt(a, t, rec["raw_log"], deck_text), False, f"ターン{t}を検討しています…")
                if ans:
                    rec.setdefault("deep_dives", {})[str(t)] = ans
                    persist()
                    st.rerun()
        dd = rec.get("deep_dives", {}).get(str(t))
        if dd:
            with st.expander(f"T{t} の深掘り", expanded=True):
                show_answer(dd)

    st.markdown("### 棋譜と評価")
    rows = []
    for t in turns:
        sc = max(-2, min(2, int(t["score"])))
        fg, bg = EV_STYLE[sc]
        who = "me" if t["player"] == "自分" else "opp"
        actions = " / ".join(E(x) for x in t.get("key_actions", []))
        better = f'<p class="better"><span class="k">より良い手</span>{E(t["better_play"])}</p>' if t.get("better_play") else ""
        flag = '<span class="flag">◆ 転換点</span>' if t["turn"] in swings else ""
        pl = t.get("prizes_left")
        prize = (f'<span class="prize">サイド残り 自分{pl[0]}・相手{pl[1]}</span>' if pl else "")
        rows.append(f"""<details><summary>
<div class="row"><span class="n">T{t['turn']}</span><span class="who {who}">{E(t['player'])}</span>
<span class="ev" style="color:{fg};background:{bg}">{E(core.eval_label(sc))}</span>{flag}<span class="chev">▾</span></div>
<div class="sum">{E(t['summary'])}{prize}</div></summary>
<div class="body"><p><span class="k">評価の根拠</span>{E(t['reason'])}</p>
{f'<p><span class="k">主な行動</span>{actions}</p>' if actions else ''}{better}</div></details>""")
    st.markdown(f'<div class="record">{"".join(rows)}</div>', unsafe_allow_html=True)
    st.markdown('<p class="hint">各ターンをタップすると、評価の根拠と「より良い手」が開きます。</p>', unsafe_allow_html=True)

    if a.get("lessons"):
        st.markdown("### 次の対戦に活かすこと")
        st.markdown('<ul class="lessons">' + "".join(f"<li>{E(x)}</li>" for x in a["lessons"]) + "</ul>",
                    unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 画面
# ---------------------------------------------------------------------------
age = core.meta_age_days(store)
brand("環境メモ未設定" if age is None else f"環境 {store.get('meta_updated_at', '')[:10]}")

tab_log, tab_hist, tab_deck, tab_meta, tab_set = st.tabs(["検討", "履歴", "デッキ", "環境", "設定"])

# --- 検討 ------------------------------------------------------------------
with tab_log:
    cur = next((r for r in store["analyses"] if r["id"] == st.session_state.get("current_id")), None)
    with st.expander("バトルログを貼り付ける" if cur is None else "別の対局を検討する", expanded=cur is None):
        st.markdown('<p class="hint">PTCGL の対戦終了画面で「バトルログ」を開き、全文をコピーして貼り付けます。</p>',
                    unsafe_allow_html=True)
        deck_sel = st.selectbox("使ったデッキ", ["指定しない"] + deck_options(), key="log_deck")
        deck_name = "" if deck_sel == "指定しない" else deck_sel
        deck_text = store["decks"].get(deck_name, "")
        raw_log = st.text_area("バトルログ", height=170, key="log_text", placeholder="ここに貼り付け")
        extra = st.text_area("補足（任意）", height=80, key="log_extra",
                             placeholder="ターン5で手札にボスの指令があった、など")
        info = ""
        if raw_log.strip():
            parsed = core.parse_log(raw_log)
            me = store["settings"].get("player_name", "")
            if parsed.ok:
                fx = core.extract_facts(parsed, me)
                last = fx["turns"][-1]
                info = (f"{len(parsed.turns)}ターン読み取り：あなた（{fx['me']}）は{fx['went_first']}・{fx['result']}・"
                        f"最終サイド残り 自分{last['my_left']}枚／相手{last['opp_left']}枚")
                if me and me not in parsed.players:
                    info += f"。設定のプレイヤー名「{me}」がログにないため、{fx['me']} を自分として扱います"
            else:
                info = "ターンの区切りを読み取れませんでしたが、このまま検討できます"
            st.markdown(f'<p class="hint">{E(info)}</p>', unsafe_allow_html=True)

        if st.button("この対局を検討する", type="primary", disabled=not raw_log.strip(), width="stretch"):
            if not need_key():
                parsed = core.parse_log(raw_log)
                facts = core.extract_facts(parsed, store["settings"].get("player_name", ""))
                prompt = core.build_analysis_prompt(core.format_log_for_ai(parsed, raw_log), facts["me"],
                                                    deck_text, store.get("meta_notes", ""), extra,
                                                    digest=core.facts_digest(facts))
                out = run_ai("1ターンずつ検討しています（20〜60秒）",
                             lambda n: core.analyze_game(api_key(), model(), prompt, store["regulation"], n,
                                                         fast=st.session_state.get("fast_mode", True)))
                if out:
                    analysis, used = out
                    analysis = core.merge_with_facts(analysis, facts)
                elif facts["turns"]:
                    # AIが使えなくても、サイドの取り合いだけで形勢は表示する
                    analysis, used = core.fallback_analysis(facts), "自動評価"
                    st.session_state.fallback_used = True
                else:
                    analysis = None
                if analysis:
                    rec = core.new_analysis_record(deck_name, raw_log, extra, analysis, used)
                    store["analyses"].insert(0, rec)
                    persist()
                    st.session_state.current_id = rec["id"]
                    st.rerun()

    if cur:
        render_analysis(cur)
    elif not store["analyses"]:
        st.markdown('<div class="empty">対局を検討すると、ここに勝敗・形勢グラフ・「打つべきだった手」が表示されます。</div>',
                    unsafe_allow_html=True)

# --- 履歴 ------------------------------------------------------------------
with tab_hist:
    recs = store["analyses"]
    if not recs:
        st.markdown('<div class="empty">まだ検討した対局がありません。「検討」タブから始めてください。</div>',
                    unsafe_allow_html=True)
    else:
        res = [r["analysis"].get("result", "-") for r in recs]
        wins, losses = res.count("勝ち"), res.count("負け")
        st.markdown(f'<div class="stats"><div>勝ち<b>{wins}</b></div><div>負け<b>{losses}</b></div>'
                    f'<div>勝率<b>{wins / max(1, wins + losses):.0%}</b></div></div>', unsafe_allow_html=True)

        mu: dict[str, list[int]] = {}
        for r in recs:
            res_ = r["analysis"].get("result")
            if res_ in ("勝ち", "負け"):
                w = mu.setdefault(r["analysis"].get("opponent_deck_guess", "不明"), [0, 0])
                w[0 if res_ == "勝ち" else 1] += 1
        if mu:
            st.markdown("### 相手デッキ別")
            rows = "".join(f'<div><span>{E(k)}</span><span><b>{v[0]}</b>勝<b>{v[1]}</b>敗</span></div>'
                           for k, v in sorted(mu.items(), key=lambda kv: -(kv[1][0] + kv[1][1])))
            st.markdown(f'<div class="mu">{rows}</div>', unsafe_allow_html=True)

        st.markdown("### 対局を開く")
        labels = [f"{r['created_at'][5:]}　{r['analysis'].get('result', '-')}　vs {r['analysis'].get('opponent_deck_guess', '-')}"
                  for r in recs]
        idx = st.selectbox("対局", range(len(recs)), format_func=lambda i: labels[i], label_visibility="collapsed")
        if st.button("この対局を表示", type="primary", width="stretch"):
            st.session_state.current_id = recs[idx]["id"]
            st.toast("「検討」タブに表示しました")
        if st.button("この対局を削除", width="stretch"):
            recs.pop(idx)
            persist()
            st.rerun()

# --- デッキ ----------------------------------------------------------------
with tab_deck:
    names = deck_options()
    with st.expander("デッキを登録・編集", expanded=not names):
        st.markdown('<p class="hint">PTCGL のデッキ編集画面で「エクスポート」したテキストを貼り付けます。</p>',
                    unsafe_allow_html=True)
        target = st.selectbox("編集するデッキ", ["新しいデッキ"] + names, key="deck_target")
        is_new = target == "新しいデッキ"
        dname = st.text_input("デッキ名", "" if is_new else target, placeholder="メガサメハダーex", key=f"dn_{target}")
        dtext = st.text_area("デッキリスト", "" if is_new else store["decks"][target], height=200, key=f"dt_{target}")
        if dtext.strip():
            d = core.parse_deck(dtext)
            cnt = d["counts"]
            ok = "ok" if d["total"] == 60 else "ng"
            st.markdown(f'<div class="deckcount"><div>ポケモン<b>{cnt["pokemon"]}</b></div><div>トレーナーズ<b>{cnt["trainer"]}</b></div>'
                        f'<div>エネルギー<b>{cnt["energy"]}</b></div><div class="{ok}">合計<b>{d["total"]}</b></div></div>',
                        unsafe_allow_html=True)
        if st.button("デッキを保存", type="primary", disabled=not (dname and dtext.strip()), width="stretch"):
            if not is_new and dname != target:
                store["decks"].pop(target, None)
            store["decks"][dname] = dtext
            persist()
            st.toast(f"「{dname}」を保存しました")
            st.rerun()
        if not is_new and st.button("このデッキを削除", width="stretch"):
            store["decks"].pop(target, None)
            persist()
            st.rerun()

    st.markdown("### 戦い方と展開")
    if not names:
        st.markdown('<div class="empty">デッキを登録すると、今の環境に合わせた戦い方を解説できます。</div>',
                    unsafe_allow_html=True)
    else:
        g_name = st.selectbox("解説するデッキ", names, key="guide_deck")
        focus = st.text_input("特に知りたいこと（任意）", placeholder="後攻1ターン目の動き", key="guide_focus")
        if st.button("戦い方を解説してもらう", type="primary", width="stretch"):
            if not need_key():
                search = not meta_is_fresh()
                ans = stream_answer(core.deck_guide_prompt(store["decks"][g_name], store.get("meta_notes", ""), focus, search),
                                    search, "最新の環境を検索してから書き始めます…" if search else "書き始めています…")
                if ans:
                    store.setdefault("guides", {})[g_name] = ans
                    persist()
                    st.rerun()
        show_answer(store.get("guides", {}).get(g_name))

# --- 環境 ------------------------------------------------------------------
with tab_meta:
    if age is None or age > 14:
        st.markdown(f'<div class="notice"><b>環境メモが{"未設定" if age is None else f"{age}日前のもの"}です。</b>'
                    '更新すると、すべての検討とアドバイスに反映されます。</div>', unsafe_allow_html=True)
    if st.button("最新の環境を調べる", type="primary", width="stretch"):
        if not need_key():
            ans = stream_answer(core.meta_research_prompt(store["regulation"]), True, "大会結果を検索しています…")
            if ans:
                st.session_state.meta_draft = ans
                st.rerun()
    draft = st.session_state.get("meta_draft")
    if draft:
        with st.container(border=True):
            show_answer(draft)
            if st.button("この内容で環境メモを更新", type="primary", width="stretch"):
                store["meta_notes"] = draft["text"]
                store["meta_updated_at"] = draft["at"][:10]
                st.session_state.meta_draft = None
                persist()
                st.rerun()

    st.markdown("### 環境を踏まえたアドバイス")
    names = deck_options()
    if not names:
        st.markdown('<div class="empty">デッキを登録すると、上位デッキとの相性や構築の調整案を出せます。</div>',
                    unsafe_allow_html=True)
    else:
        m_name = st.selectbox("デッキ", names, key="meta_deck")
        if st.button("アドバイスをもらう", type="primary", width="stretch"):
            if not need_key():
                search = not meta_is_fresh()
                ans = stream_answer(core.meta_advice_prompt(store["decks"][m_name], store.get("meta_notes", ""), search),
                                    search, "最新の環境を検索してから書き始めます…" if search else "書き始めています…")
                if ans:
                    store.setdefault("meta_advice", {})[m_name] = ans
                    persist()
                    st.rerun()
        show_answer(store.get("meta_advice", {}).get(m_name))

    st.markdown("### 保存している環境メモ")
    with st.expander(f"環境メモ（{store.get('meta_updated_at', '-')[:10]}）"):
        notes = st.text_area("環境メモ", store.get("meta_notes", ""), height=260, label_visibility="collapsed",
                             key="meta_notes_edit")
        if st.button("メモを保存", width="stretch"):
            store["meta_notes"] = notes
            persist()
            st.toast("環境メモを保存しました")
    with st.expander("レギュレーション"):
        reg = st.text_area("使用可能なカードの範囲", store["regulation"], height=110, label_visibility="collapsed",
                           key="reg_edit")
        if st.button("レギュレーションを保存", width="stretch"):
            store["regulation"] = reg
            persist()
            st.toast("保存しました")

# --- 設定 ------------------------------------------------------------------
with tab_set:
    st.markdown("### プレイヤー")
    name = st.text_input("自分のプレイヤー名（ログの表記と同じに）", store["settings"].get("player_name", ""), key="player_name")
    if name != store["settings"].get("player_name"):
        store["settings"]["player_name"] = name
        persist()

    st.markdown("### AI")
    if SECRET_KEY:
        st.markdown('<p class="hint">APIキーは Secrets に登録済みです。</p>', unsafe_allow_html=True)
    else:
        st.text_input("Gemini APIキー", type="password", key="api_key_input",
                      help="Streamlit Cloud の Secrets に GEMINI_API_KEY を登録すると、毎回の入力が不要になります")
    st.selectbox("AIモデル", MODEL_CHOICES, key="model_sel",
                 help="いちばん速いのは gemini-3.5-flash-lite。混雑や上限エラーのときは自動で切り替えます")
    st.toggle("速さを優先する", value=True, key="fast_mode",
              help="対局の検討で、AIが考える時間を短くします。じっくり検討させたいときはオフにしてください")

    st.markdown("### データ")
    st.markdown('<p class="hint">公開版はアプリの再起動でデータが消えることがあります。検討のあとにバックアップを保存してください。</p>',
                unsafe_allow_html=True)
    st.download_button("バックアップを保存", json.dumps(store, ensure_ascii=False, indent=2),
                       file_name="ptcgl_backup.json", mime="application/json", width="stretch")
    up = st.file_uploader("バックアップから復元", type="json")
    if up is not None and st.button("復元する", width="stretch"):
        try:
            restored = core.default_store()
            restored.update(json.load(up))
            st.session_state.store = restored
            core.save_store(restored)
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"復元できませんでした。バックアップのファイルか確認してください。（{e}）")
