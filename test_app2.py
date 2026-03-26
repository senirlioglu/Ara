import streamlit as st
import time

# Wait for Streamlit to start up fully

st.markdown("""
<style>
    /* CSS logic testing */
</style>
""", unsafe_allow_html=True)

with st.form("arama_form", clear_on_submit=False):
    col1, col2 = st.columns([5, 1])
    with col1:
        st.text_input("Arama")
    with col2:
        st.form_submit_button("Ara")

st.markdown('<div class="popular-pill-anchor">🔥 Popüler Aramalar</div>', unsafe_allow_html=True)
cols_pop = st.columns(5)
for i in range(5):
    cols_pop[i].button(f"btn {i}")
