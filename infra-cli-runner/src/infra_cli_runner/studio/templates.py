"""Ready-made motion-graphics scenes, so an agent sends a few words instead of writing HTML.

Every animation is a CSS animation with a fixed start, which is what lets the scene renderer seek to any frame and get
the same picture each time. Each template is one class; `template_for` picks by name.
"""

from __future__ import annotations

from html import escape
from typing import Protocol

from src.infra_cli_runner.studio.models import SceneParams

EXIT_SECONDS = 0.45
FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
THEMES = {
    "dark": {"background": "linear-gradient(135deg, #0b1020 0%, #1a1f4d 100%)", "ink": "#ffffff", "muted": "#cbd5e1"},
    "light": {"background": "linear-gradient(135deg, #f8fafc 0%, #e0e7ff 100%)", "ink": "#0f172a", "muted": "#475569"},
}


class SceneTemplate(Protocol):
    name: str
    #: Rendered with an alpha channel, to be laid over footage.
    transparent: bool

    def html(self, params: SceneParams, duration: float) -> str: ...


def _page(body_css: str, body: str, duration: float, *, transparent: bool, background: str = "transparent") -> str:
    exit_delay = max(duration - EXIT_SECONDS, 0)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0}}
html,body{{width:100vw;height:100vh;overflow:hidden;background:{"transparent" if transparent else background};font-family:{FONT}}}
@keyframes rise{{from{{opacity:0;transform:translateY(4vh)}}to{{opacity:1;transform:none}}}}
@keyframes slide{{from{{opacity:0;transform:translateX(-5vw)}}to{{opacity:1;transform:none}}}}
@keyframes grow{{from{{width:0}}to{{width:9vw}}}}
@keyframes pop{{from{{opacity:0;transform:scale(.86)}}to{{opacity:1;transform:none}}}}
@keyframes leave{{from{{opacity:1}}to{{opacity:0}}}}
@keyframes drift{{from{{transform:translate(-3vw,-2vh)}}to{{transform:translate(3vw,2vh)}}}}
.stage{{position:absolute;inset:0;animation:leave {EXIT_SECONDS}s ease-in {exit_delay:.3f}s both}}
{body_css}
</style></head><body><div class="stage">{body}</div></body></html>"""


class TitleTemplate:
    name = "title"
    transparent = False

    def html(self, params: SceneParams, duration: float) -> str:
        theme = THEMES[params.theme]
        css = f"""
.glow{{position:absolute;width:60vw;height:60vw;left:20vw;top:-10vw;border-radius:50%;
  background:radial-gradient({params.accent}55,transparent 65%);animation:drift {duration:.3f}s linear both}}
.copy{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:0 9vw}}
h1{{font-size:5.4vw;line-height:1.08;letter-spacing:-.025em;font-weight:800;color:{theme["ink"]};animation:rise .9s cubic-bezier(.2,.8,.2,1) both}}
.bar{{height:.5vw;margin:3vh 0 2.6vh;border-radius:1vw;background:{params.accent};animation:grow .8s cubic-bezier(.2,.8,.2,1) .25s both}}
p{{font-size:2.1vw;line-height:1.35;color:{theme["muted"]};max-width:60vw;animation:rise .9s cubic-bezier(.2,.8,.2,1) .4s both}}
.eyebrow{{font-size:1.4vw;letter-spacing:.3em;text-transform:uppercase;font-weight:700;color:{params.accent};margin-bottom:2.4vh;animation:rise .8s ease-out both}}"""
        eyebrow = f'<div class="eyebrow">{escape(params.eyebrow)}</div>' if params.eyebrow else ""
        subheading = f"<p>{escape(params.subheading)}</p>" if params.subheading else ""
        body = f'<div class="glow"></div><div class="copy">{eyebrow}<h1>{escape(params.heading)}</h1><div class="bar"></div>{subheading}</div>'
        return _page(css, body, duration, transparent=False, background=theme["background"])


class OutroTemplate:
    name = "outro"
    transparent = False

    def html(self, params: SceneParams, duration: float) -> str:
        theme = THEMES[params.theme]
        css = f"""
.glow{{position:absolute;width:70vw;height:70vw;left:15vw;top:15vh;border-radius:50%;
  background:radial-gradient({params.accent}44,transparent 62%);animation:drift {duration:.3f}s linear both}}
.copy{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:0 9vw}}
h1{{font-size:5vw;line-height:1.1;letter-spacing:-.025em;font-weight:800;color:{theme["ink"]};animation:rise .9s cubic-bezier(.2,.8,.2,1) both}}
p{{margin-top:2.4vh;font-size:2vw;color:{theme["muted"]};animation:rise .9s cubic-bezier(.2,.8,.2,1) .3s both}}
.cta{{margin-top:5vh;padding:1.6vh 3.2vw;border-radius:5vw;background:{params.accent};color:#fff;font-size:2.3vw;font-weight:700;
  animation:pop .7s cubic-bezier(.2,.9,.3,1.2) .7s both}}"""
        subheading = f"<p>{escape(params.subheading)}</p>" if params.subheading else ""
        cta = f'<div class="cta">{escape(params.footer)}</div>' if params.footer else ""
        body = f'<div class="glow"></div><div class="copy"><h1>{escape(params.heading)}</h1>{subheading}{cta}</div>'
        return _page(css, body, duration, transparent=False, background=theme["background"])


class LowerThirdTemplate:
    name = "lower_third"
    transparent = True

    def html(self, params: SceneParams, duration: float) -> str:
        css = f"""
.card{{position:absolute;left:4vw;bottom:8vh;max-width:62vw;padding:1.8vh 2.2vw;border-radius:.8vw;
  background:rgba(11,16,32,.9);border-left:.55vw solid {params.accent};box-shadow:0 1.2vh 3vh rgba(0,0,0,.35);
  animation:slide .6s cubic-bezier(.2,.8,.2,1) .15s both}}
h1{{font-size:2.5vw;line-height:1.15;font-weight:800;color:#fff;letter-spacing:-.01em}}
p{{margin-top:.7vh;font-size:1.55vw;line-height:1.3;color:#cbd5e1}}"""
        subheading = f"<p>{escape(params.subheading)}</p>" if params.subheading else ""
        body = f'<div class="card"><h1>{escape(params.heading)}</h1>{subheading}</div>'
        return _page(css, body, duration, transparent=True)


SCENE_TEMPLATES: list[SceneTemplate] = [TitleTemplate(), OutroTemplate(), LowerThirdTemplate()]


def template_for(name: str) -> SceneTemplate:
    return next(template for template in SCENE_TEMPLATES if template.name == name)
