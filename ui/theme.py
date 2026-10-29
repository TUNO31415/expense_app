from __future__ import annotations

import streamlit as st

ACCENT = "#2DD4BF"
MUTED = "#8B90A0"
FALLBACK_COLORS = ["#A78BFA", "#F472B6", "#FBBF24", "#60A5FA", "#F87171", "#34D399"]

TYPE_COLORS = {
    "Fixed Costs": "#60A5FA",
    "Variable Costs": "#2DD4BF",
    "One time Costs": "#FBBF24",
    "Savings": "#A78BFA",
    "Other": MUTED,
}

_CSS = """
<style>
.block-container { padding-top: 2.2rem; padding-bottom: 2rem; max-width: 1400px; }
footer { visibility: hidden; }
[data-testid="stMetricValue"] { font-size: 1.75rem; font-weight: 600; }
[data-testid="stMetricLabel"] p { color: #8B90A0; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.04em; }
.page-subtitle { color: #8B90A0; margin-top: -0.6rem; margin-bottom: 1.2rem; }
.empty-state { text-align: center; padding: 2.5rem 1rem; color: #8B90A0; }
.empty-state .icon { font-size: 2.5rem; }
</style>
"""


def inject_css() -> None:
    """Add the small set of style tweaks the theme config can't express."""
    st.markdown(_CSS, unsafe_allow_html=True)


def color_for_type(type_name: str | None) -> str:
    """Return the chart colour for a type, with stable fallbacks for user-created types."""
    if type_name in TYPE_COLORS:
        return TYPE_COLORS[type_name]
    name = str(type_name or "")
    return FALLBACK_COLORS[sum(map(ord, name)) % len(FALLBACK_COLORS)]


def type_color_map(type_names) -> dict[str, str]:
    """Build a Plotly colour map for the given type names."""
    return {name: color_for_type(name) for name in type_names}


def plotly_layout(fig):
    """Apply the shared dark chart styling and return the figure."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#E6E8EE"),
        margin=dict(t=10, b=10, l=10, r=10),
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, title_text=""),
        hoverlabel=dict(font_family="Inter, sans-serif"),
    )
    fig.update_xaxes(showgrid=False, title_text="")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)", title_text="")
    return fig
