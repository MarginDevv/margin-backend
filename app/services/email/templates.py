"""HTML email templates rendered with Jinja2."""
from __future__ import annotations

from jinja2 import Environment, select_autoescape

_env = Environment(autoescape=select_autoescape(["html", "xml"]))

_VERIFY_HTML = _env.from_string("""
<!DOCTYPE html>
<html lang="ru">
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
             max-width: 560px; margin: 0 auto; padding: 32px 24px; color: #1a1a1a;">
  <h1 style="font-size: 24px; margin: 0 0 16px;">Подтвердите email</h1>
  <p style="font-size: 16px; line-height: 1.5; margin: 0 0 24px;">
    Привет{% if name %}, {{ name }}{% endif %}!<br>
    Чтобы завершить регистрацию в <b>Margin</b>, подтверди свой email — это поможет
    нам прислать тебе отчёты и рекомендации, если что-то пойдёт не так с Telegram.
  </p>
  <p style="margin: 0 0 32px;">
    <a href="{{ verify_url }}"
       style="display:inline-block; background:#2563eb; color:#ffffff;
              padding:12px 28px; border-radius:8px; text-decoration:none;
              font-weight:600;">
      Подтвердить email
    </a>
  </p>
  <p style="font-size: 13px; color: #6b7280; margin: 0 0 8px;">
    Ссылка действует {{ ttl_hours }} часа. Если ты не регистрировался — просто
    проигнорируй это письмо.
  </p>
  <p style="font-size: 13px; color: #6b7280; margin: 0;">
    Если кнопка не работает, скопируй ссылку в браузер:<br>
    <span style="word-break: break-all;">{{ verify_url }}</span>
  </p>
</body>
</html>
""".strip())


_VERIFY_TEXT = _env.from_string(
    "Привет{% if name %}, {{ name }}{% endif %}!\n\n"
    "Подтверди email, перейдя по ссылке (действует {{ ttl_hours }} часа):\n"
    "{{ verify_url }}\n\n"
    "Если ты не регистрировался в Margin, просто проигнорируй это письмо."
)


def render_verification(name: str | None, verify_url: str, ttl_hours: int) -> tuple[str, str]:
    """Returns (html_body, text_body)."""
    ctx = {"name": name, "verify_url": verify_url, "ttl_hours": ttl_hours}
    return _VERIFY_HTML.render(**ctx), _VERIFY_TEXT.render(**ctx)


_RESET_HTML = _env.from_string("""
<!DOCTYPE html>
<html lang="ru">
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
             max-width: 560px; margin: 0 auto; padding: 32px 24px; color: #1a1a1a;">
  <h1 style="font-size: 24px; margin: 0 0 16px;">Сброс пароля</h1>
  <p style="font-size: 16px; line-height: 1.5; margin: 0 0 24px;">
    {% if name %}{{ name }}, н{% else %}Н{% endif %}а аккаунт {{ email }} был запрошен сброс пароля.
    Нажми на кнопку, чтобы задать новый.
  </p>
  <p style="margin: 0 0 32px;">
    <a href="{{ reset_url }}"
       style="display:inline-block; background:#2563eb; color:#ffffff;
              padding:12px 28px; border-radius:8px; text-decoration:none;
              font-weight:600;">
      Задать новый пароль
    </a>
  </p>
  <p style="font-size: 13px; color: #6b7280; margin: 0 0 8px;">
    Ссылка действует {{ ttl_hours }} час{% if ttl_hours == 1 %}{% elif ttl_hours < 5 %}а{% else %}ов{% endif %}.
    Если ты не запрашивал сброс — просто проигнорируй это письмо,
    пароль останется прежним.
  </p>
  <p style="font-size: 13px; color: #6b7280; margin: 0;">
    Если кнопка не работает, скопируй ссылку в браузер:<br>
    <span style="word-break: break-all;">{{ reset_url }}</span>
  </p>
</body>
</html>
""".strip())


_RESET_TEXT = _env.from_string(
    "{% if name %}{{ name }}, н{% else %}Н{% endif %}а аккаунт {{ email }} "
    "запрошен сброс пароля.\n\n"
    "Перейди по ссылке, чтобы задать новый (действует {{ ttl_hours }}ч):\n"
    "{{ reset_url }}\n\n"
    "Если ты не запрашивал сброс — проигнорируй это письмо."
)


def render_password_reset(
    name: str | None, email: str, reset_url: str, ttl_hours: int
) -> tuple[str, str]:
    """Returns (html_body, text_body)."""
    ctx = {"name": name, "email": email, "reset_url": reset_url, "ttl_hours": ttl_hours}
    return _RESET_HTML.render(**ctx), _RESET_TEXT.render(**ctx)
