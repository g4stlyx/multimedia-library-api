from __future__ import annotations

import asyncio
import logging
import sys
import requests
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import SessionLocal
from app.models.media import MediaType
from app.repositories.media_repository import MediaRepository
from app.services.media_service import MediaService

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# 30 classic books to seed
MOCK_BOOKS = [
    ("The Hobbit", 1937, "Fantasy", "J.R.R. Tolkien", "A quiet hobbit on an unexpected adventure."),
    ("1984", 1949, "Dystopian", "George Orwell", "A chilling look at a totalitarian future ruled by Big Brother."),
    ("To Kill a Mockingbird", 1960, "Classic", "Harper Lee", "A story of racial injustice and growing up in the American South."),
    ("The Great Gatsby", 1925, "Classic", "F. Scott Fitzgerald", "A critique of the American Dream in the roaring twenties."),
    ("Pride and Prejudice", 1813, "Romance", "Jane Austen", "A classic comedy of manners and romance between Elizabeth Bennet and Mr. Darcy."),
    ("The Lord of the Rings", 1954, "Fantasy", "J.R.R. Tolkien", "An epic quest to destroy the One Ring and defeat Sauron."),
    ("Animal Farm", 1945, "Political Satire", "George Orwell", "A group of farm animals rebel against their human farmer."),
    ("Brave New World", 1932, "Dystopian", "Aldous Huxley", "A futuristic society based on conditioning, consumerism, and technology."),
    ("Fahrenheit 451", 1953, "Sci-Fi", "Ray Bradbury", "A future society where books are outlawed and firemen burn them."),
    ("Crime and Punishment", 1866, "Psychological Fiction", "Fyodor Dostoevsky", "The mental anguish and moral dilemmas of Raskolnikov."),
    ("The Catcher in the Rye", 1951, "Classic", "J.D. Salinger", "Holden Caulfield's journey through teenage rebellion and alienation."),
    ("The Picture of Dorian Gray", 1890, "Gothic", "Oscar Wilde", "A young man sells his soul so his portrait will age instead of him."),
    ("Frankenstein", 1818, "Gothic", "Mary Shelley", "A scientist creates a creature and struggles with the consequences."),
    ("Dracula", 1897, "Gothic", "Bram Stoker", "Count Dracula's attempt to move from Transylvania to England."),
    ("The Odyssey", -800, "Mythology", "Homer", "Odysseus' ten-year journey home after the Trojan War."),
    ("The Iliad", -800, "Mythology", "Homer", "The story of the Trojan War and the wrath of Achilles."),
    ("Moby-Dick", 1851, "Adventure", "Herman Melville", "Captain Ahab's obsessive quest to destroy the white whale."),
    ("The Grapes of Wrath", 1939, "Classic", "John Steinbeck", "A poor family of tenant farmers driven from their Oklahoma home."),
    ("Jane Eyre", 1847, "Romance", "Charlotte Brontë", "The emotional and spiritual growth of orphan Jane Eyre."),
    ("Wuthering Heights", 1847, "Gothic", "Emily Brontë", "The passionate and destructive love between Heathcliff and Catherine."),
    ("Catch-22", 1961, "Satire", "Joseph Heller", "A satirical war novel set during World War II."),
    ("The Stranger", 1942, "Absurdist", "Albert Camus", "A detached clerk commits a murder on an Algerian beach."),
    ("The Metamorphosis", 1915, "Absurdist", "Franz Kafka", "A salesman wakes up to find himself transformed into a giant insect."),
    ("One Hundred Years of Solitude", 1967, "Magical Realism", "Gabriel García Márquez", "The history of the Buendía family in Macondo."),
    ("The Old Man and the Sea", 1952, "Classic", "Ernest Hemingway", "An aging Cuban fisherman struggles with a giant marlin."),
    ("Lolita", 1955, "Classic", "Vladimir Nabokov", "A literature professor becomes obsessed with a young girl."),
    ("The Bell Jar", 1963, "Classic", "Sylvia Plath", "A semi-autobiographical novel detailing a descent into mental illness."),
    ("Dune", 1965, "Sci-Fi", "Frank Herbert", "A young man's family accepts control of the desert planet Arrakis."),
    ("Neuromancer", 1984, "Cyberpunk", "William Gibson", "A washed-up computer hacker is hired for a final job."),
    ("The Road", 2006, "Post-Apocalyptic", "Cormac McCarthy", "A father and son walk through burned America.")
]

# 30 classic games to seed
MOCK_GAMES = [
    ("The Witcher 3: Wild Hunt", 2015, "RPG", "CD Projekt Red", "Geralt searches for his adopted daughter on the run from the Wild Hunt."),
    ("Portal 2", 2011, "Puzzle", "Valve", "Players solve puzzles using portal guns while navigating Aperture Science."),
    ("The Legend of Zelda: Breath of the Wild", 2017, "Adventure", "Nintendo", "Link wakes up from a century-long slumber to defeat Calamity Ganon."),
    ("Elden Ring", 2022, "RPG", "FromSoftware", "A Tarnished seeks to restore the Elden Ring and become Elden Lord."),
    ("Grand Theft Auto V", 2013, "Action", "Rockstar Games", "Three criminals pull off heists in the city of Los Santos."),
    ("Red Dead Redemption 2", 2018, "Action", "Rockstar Games", "Arthur Morgan and the Van der Linde gang navigate the decline of the Wild West."),
    ("Minecraft", 2011, "Sandbox", "Mojang", "Players build, explore, craft, and survive in a blocky 3D world."),
    ("The Elder Scrolls V: Skyrim", 2011, "RPG", "Bethesda", "The Dragonborn seeks to defeat Alduin the World-Eater."),
    ("Half-Life 2", 2004, "Shooter", "Valve", "Gordon Freeman fights against the alien Combine occupying Earth."),
    ("Super Mario Odyssey", 2017, "Platformer", "Nintendo", "Mario travels across worlds with Cappy to rescue Princess Peach."),
    ("Hades", 2020, "Rogue-like", "Supergiant Games", "Zagreus attempts to escape the Underworld of his father Hades."),
    ("God of War", 2018, "Action", "Santa Monica Studio", "Kratos and his son Atreus journey to scatter his wife's ashes."),
    ("Doom Eternal", 2020, "Shooter", "id Software", "The Doom Slayer battles the forces of Hell invading Earth."),
    ("Chrono Trigger", 1995, "RPG", "Square", "A group of adventurers travel through time to prevent global catastrophe."),
    ("Mass Effect 2", 2010, "Sci-Fi RPG", "BioWare", "Commander Shepard assembles a team for a suicide mission against the Collectors."),
    ("Disco Elysium", 2019, "RPG", "ZA/UM", "An amnesiac detective solves a murder while dealing with personal demons."),
    ("Dark Souls", 2011, "RPG", "FromSoftware", "The Chosen Undead journeys through the dying world of Lordran."),
    ("BioShock", 2007, "Shooter", "2K Games", "Jack survives a plane crash and discovers the decaying underwater city of Rapture."),
    ("The Last of Us", 2013, "Action", "Naughty Dog", "Joel escorts teenage Ellie across a post-apocalyptic United States."),
    ("Metal Gear Solid", 1998, "Stealth", "Konami", "Solid Snake infiltrates a nuclear weapons disposal facility."),
    ("Super Metroid", 1994, "Metroidvania", "Nintendo", "Samus Aran travels to planet Zebes to retrieve a stolen Metroid larva."),
    ("Shadow of the Colossus", 2005, "Adventure", "Team Ico", "Wander seeks to revive a girl by defeating sixteen giant colossi."),
    ("Undertale", 2015, "RPG", "Toby Fox", "A child falls into the Underworld filled with monsters."),
    ("Resident Evil 4", 2005, "Horror", "Capcom", "Leon S. Kennedy rescues the US President's daughter from a cult."),
    ("Fallout: New Vegas", 2010, "RPG", "Obsidian Entertainment", "A courier seeks revenge in the Mojave Wasteland."),
    ("Hollow Knight", 2017, "Metroidvania", "Team Cherry", "A nameless knight explores the ruined kingdom of Hallownest."),
    ("Deus Ex", 2000, "RPG", "Ion Storm", "JC Denton battles a virus conspiracy in a cyberpunk world."),
    ("Street Fighter II", 1991, "Fighting", "Capcom", "Martial artists compete in a global tournament."),
    ("Tetris", 1984, "Puzzle", "Alexey Pajitnov", "Players stack falling blocks of different shapes."),
    ("World of Warcraft", 2004, "MMORPG", "Blizzard", "Players explore the fantasy world of Azeroth.")
]


async def seed_tmdb_media(db: Session, media_type: MediaType, endpoint_path: str, count: int = 100) -> None:
    settings = get_settings()
    if not settings.tmdb_api_key:
        logger.error("TMDB_API_KEY environment variable is not set. Skipping TMDB seed.")
        return

    service = MediaService(db, settings)
    api_key = settings.tmdb_api_key
    
    # We fetch page by page until we reach 'count' IDs
    seen_ids = []
    page = 1
    
    logger.info("Fetching popular TMDB ID list for %s...", media_type.name)
    while len(seen_ids) < count and page <= 10:
        url = f"https://api.themoviedb.org/3{endpoint_path}"
        params = {"api_key": api_key, "page": page}
        try:
            res = requests.get(url, params=params, timeout=10)
            res.raise_for_status()
            results = res.json().get("results", [])
            if not results:
                break
            for r in results:
                val = str(r.get("id"))
                if val and val not in seen_ids:
                    seen_ids.append(val)
            page += 1
        except Exception as e:
            logger.error("Failed to fetch popular list page %d from TMDB: %s", page, e)
            break

    target_ids = seen_ids[:count]
    logger.info("Fetched %d unique IDs. Starting details imports sequentially...", len(target_ids))

    for tid in target_ids:
        try:
            await service.upsert_by_external_id(
                provider="tmdb",
                external_id=tid,
                media_type=media_type,
            )
            logger.info("Successfully imported TMDB %s ID: %s", media_type.value, tid)
        except Exception as e:
            logger.error("Failed to import TMDB %s ID %s: %s", media_type.value, tid, e)
            db.rollback()



def seed_mock_media(db: Session, media_type: MediaType, items: list) -> None:
    repo = MediaRepository(db)
    logger.info("Seeding %d mock %ss...", len(items), media_type.name)
    
    for title, year, genre_name, creator, desc in items:
        # Check if already seeded
        normalized = title.strip().lower()
        existing = repo.get_by_external_id(f"mock_{media_type.value.lower()}", normalized)
        if existing:
            continue

        media = repo.create_media(
            media_type=media_type,
            canonical_title=title,
            release_year=year,
            description=desc,
            metadata_json={"creator": creator},
        )
        # Add external ID
        repo.add_external_id(
            media_id=media.id,
            provider=f"mock_{media_type.value.lower()}",
            external_id=normalized,
        )
        # Add primary title
        repo.add_title(
            media_id=media.id,
            title=title,
            is_primary=True,
        )
        # Get/create and associate genre
        genre = repo.get_or_create_genre(genre_name)
        repo.associate_genre(media, genre)

    db.commit()
    logger.info("Successfully seeded mock %ss.", media_type.name)


async def main() -> None:
    db = SessionLocal()
    try:
        # 1. Seed movies (100 popular movies from TMDB)
        logger.info("=== Seeding Movies ===")
        await seed_tmdb_media(db, MediaType.MOVIE, "/movie/popular", 100)

        # 2. Seed series (100 popular TV series from TMDB)
        logger.info("=== Seeding Series ===")
        await seed_tmdb_media(db, MediaType.SERIES, "/tv/popular", 100)

        # 3. Seed books (30 high-quality classic books)
        logger.info("=== Seeding Books ===")
        seed_mock_media(db, MediaType.BOOK, MOCK_BOOKS)

        # 4. Seed games (30 high-quality classic video games)
        logger.info("=== Seeding Games ===")
        seed_mock_media(db, MediaType.GAME, MOCK_GAMES)

        logger.info("=== Seeding Completed Successfully! ===")
    except Exception as e:
        logger.exception("Seeding script failed: %s", e)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
