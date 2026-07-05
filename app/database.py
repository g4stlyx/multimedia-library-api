from sqlalchemy import create_backend, engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Docker'da açtığımız Postgres adresi
SQLALCHEMY_DATABASE_URL = "postgresql://g4stly:12345678@localhost:5432/multimedia_app"

engine = create_backend(SQLALCHEMY_DATABASE_URL)

# Spring'deki EntityManager/Session yapısının muadili
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Hızlıca DB Session yönetimi sağlayan Dependency Injection fonksiyonu
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()