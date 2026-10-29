from __future__ import annotations

from typing import Any

import streamlit as st

from ui.feedback import show_flash
from ui.theme import inject_css


def fmt_eur(amount_eur: float) -> str:
    """Format a euro amount for display."""
    return f"€{amount_eur:,.2f}"


def fmt_eur_whole(amount_eur: float) -> str:
    """Format a euro amount without cents, for chart labels and dense tables."""
    return f"€{amount_eur:,.0f}"


def page_header(title: str, subtitle: str | None = None) -> None:
    """Start a page: shared CSS, any pending flash message, and the title block."""
    inject_css()
    show_flash()
    st.title(title)
    if subtitle:
        st.markdown(f'<p class="page-subtitle">{subtitle}</p>', unsafe_allow_html=True)


def kpi_card(label: str, value: str, delta: str | None = None, delta_color: str = "normal", help: str | None = None) -> None:
    """Render a bordered metric card."""
    st.metric(label, value, delta=delta, delta_color=delta_color, border=True, help=help)


def empty_state(icon: str, text: str, action_label: str | None = None, page: str | None = None) -> None:
    """Render a centred empty-state message with an optional link to another page."""
    with st.container(border=True):
        st.markdown(
            f'<div class="empty-state"><div class="icon">{icon}</div><p>{text}</p></div>',
            unsafe_allow_html=True,
        )
        if action_label and page:
            st.page_link(page, label=action_label, icon=":material/arrow_forward:")


def badge_row(badges: list[tuple[str, str | None, str]]) -> None:
    """Render (label, icon, color) badges side by side."""
    with st.container(horizontal=True, gap="small"):
        for label, icon, color in badges:
            st.badge(label, icon=icon, color=color)


def category_label(category: dict[str, Any]) -> str:
    """Return the combined 'Type / Category' label used in dropdowns."""
    return f"{category['type_name']} / {category['name']}"


def category_label_map(categories: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map 'Type / Category' labels to category rows, in display order."""
    return {category_label(category): category for category in categories}
