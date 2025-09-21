import asyncio
from datetime import datetime, timezone

from app.notifier import AlertEvent, build_notifier_from_env


async def main() -> None:
	notifier = build_notifier_from_env()
	event = AlertEvent(
		service_id=1,
		level="info",
		title="Тестовое уведомление",
		message="Проверка отправки сообщения",
		ts=datetime.now(timezone.utc),
	)
	await notifier.send(event)


if __name__ == "__main__":
	asyncio.run(main()) 