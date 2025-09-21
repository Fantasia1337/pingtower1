from __future__ import annotations

from app.db.models import Base, engine
from app.db import repo


def main() -> None:
	Base.metadata.create_all(engine)
	services = [
		("Example", "https://example.com", 60, 5),
		("GitHub", "https://github.com", 60, 5),
		("VK", "https://vk.com", 60, 5),
	]
	for name, url, interval, timeout in services:
		repo.create_service(name, url, interval, timeout)
	print("Seeded demo services.")


if __name__ == "__main__":
	main() 