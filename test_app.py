import streamlit as st

st.markdown("""
<style>
    /* OLD BROKEN CSS SIMULATION */
    /* [data-testid="stVerticalBlock"]:has(.popular-pill-anchor) [data-testid="stHorizontalBlock"] { background: red; } */

    /* NEW CSS */
    [data-testid="stElementContainer"]:has(.popular-pill-anchor) + [data-testid="stHorizontalBlock"] {
        background: yellow;
    }
    [data-testid="stElementContainer"]:has(.popular-pill-anchor) + [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        border: 2px solid green;
    }

    [data-testid="stElementContainer"]:has(.week-tab-anchor) + [data-testid="stHorizontalBlock"] {
        background: lightblue;
    }
</style>
""", unsafe_allow_html=True)

with st.form("arama_form", clear_on_submit=False):
    col1, col2 = st.columns([5, 1])
    with col1:
        st.text_input("Arama")
    with col2:
        st.form_submit_button("🔍 Ara")

st.markdown('<div class="popular-pill-anchor">🔥 Popüler Aramalar</div>', unsafe_allow_html=True)
cols_pop = st.columns(5)
for i in range(5):
    cols_pop[i].button(f"btn {i}")

st.markdown('<div class="week-tab-anchor"></div>', unsafe_allow_html=True)
tab_cols = st.columns(3)
for i in range(3):
    tab_cols[i].button(f"tab {i}")
