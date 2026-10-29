from __future__ import annotations

import streamlit as st

_FLASH_KEY = "_flash_messages"


def flash(message: str, icon: str = ":material/check_circle:") -> None:
    """Queue a toast that survives the next st.rerun()."""
    st.session_state.setdefault(_FLASH_KEY, []).append((message, icon))


def show_flash() -> None:
    """Show and clear any queued toasts."""
    for message, icon in st.session_state.pop(_FLASH_KEY, []):
        st.toast(message, icon=icon)


def after_write(message: str | None = None, icon: str = ":material/check_circle:") -> None:
    """Finish a database write: queue feedback, drop cached data and rerun."""
    if message:
        flash(message, icon)
    st.cache_data.clear()
    st.rerun()
