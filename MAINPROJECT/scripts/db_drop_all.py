from app.db.models import Base, engine


def main() -> None:
    Base.metadata.drop_all(engine)


if __name__ == "__main__":
    main() 