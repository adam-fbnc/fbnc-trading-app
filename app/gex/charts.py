"""
Chart rendering layer — isolated so it can be replaced by Streamlit/Dash
without touching calculator.py or service.py.

To upgrade to Streamlit (Option C): import GEXResult from calculator,
call calculate_gex() from service, and render with st.plotly_chart().

To upgrade to Dash (Option D): use the same data, wrap in dcc.Graph().
"""
from decimal import Decimal

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from app.gex.calculator import GEXResult


def build_gex_chart(result: GEXResult) -> str:
    """Return a self-contained HTML string with the embedded Plotly chart."""
    strikes = [float(r.strike) for r in result.strikes]
    call_gex = [float(r.call_gex) / 1_000_000 for r in result.strikes]  # scale to $M
    put_gex = [float(r.put_gex) / 1_000_000 for r in result.strikes]
    net_gex = [float(r.net_gex) / 1_000_000 for r in result.strikes]

    spot = float(result.spot_price)
    flip = float(result.gamma_flip) if result.gamma_flip else None
    total = float(result.total_gex) / 1_000_000

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Call GEX bars (green)
    fig.add_trace(go.Bar(
        x=strikes, y=call_gex,
        name="Call GEX",
        marker_color="rgba(0, 180, 100, 0.7)",
    ), secondary_y=False)

    # Put GEX bars (red)
    fig.add_trace(go.Bar(
        x=strikes, y=put_gex,
        name="Put GEX",
        marker_color="rgba(220, 50, 50, 0.7)",
    ), secondary_y=False)

    # Net GEX line overlay
    fig.add_trace(go.Scatter(
        x=strikes, y=net_gex,
        name="Net GEX",
        mode="lines+markers",
        line=dict(color="white", width=2),
        marker=dict(size=4),
    ), secondary_y=False)

    # Spot price line
    fig.add_vline(
        x=spot, line_dash="dash", line_color="yellow", line_width=2,
        annotation_text=f"Spot {spot:,.2f}",
        annotation_position="top right",
        annotation_font_color="yellow",
    )

    # Gamma flip line
    if flip:
        fig.add_vline(
            x=flip, line_dash="dot", line_color="cyan", line_width=2,
            annotation_text=f"Flip {flip:,.2f}",
            annotation_position="top left",
            annotation_font_color="cyan",
        )

    total_sign = "+" if total >= 0 else ""
    title = (
        f"{result.symbol} Gamma Exposure  |  "
        f"Total GEX: {total_sign}{total:,.1f}M  |  "
        f"Spot: {spot:,.2f}"
        + (f"  |  Gamma Flip: {flip:,.2f}" if flip else "")
    )

    fig.update_layout(
        title=title,
        barmode="relative",
        template="plotly_dark",
        xaxis_title="Strike",
        yaxis_title="GEX ($ Millions)",
        legend=dict(orientation="h", y=1.1),
        hovermode="x unified",
        height=600,
    )

    return fig.to_html(full_html=True, include_plotlyjs="cdn")
