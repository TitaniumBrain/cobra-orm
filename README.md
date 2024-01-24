# CobraORM

CobraORM is a simple, asynchronous ORM for `aiosqlite` with a big focus on type hinting and autocompletion.

*Tired of constantly having to double check the name of a column in a table? Did you forget that column may be null?*

*Then CobraORM may be for you!*

It currently doesn't have full SQL support, but that may change in the future.

## Features

* Create models (tables) with integer, real and text fields (columns);
* Fields can be optional and have a default value;
* Fields may be specified to accept a null value;
* SELECT, DELETE, UPDATE and INSERT statements with proper type hinting according to the respective model;
* Fluent interface (method chaining) construction of statements:
    * ORDER BY
    * LIMIT

## Example usage

Let's start by connecting to an in-memory database:

```python
import aiosqlite
import asyncio
from cobra_orm import Model, Text, Real, Integer

async def connect_to_database():
    db_connection = await aiosqlite.connect(":memory:")
    return db_connection

async def main():
    db_conn = await connect_to_database()

    # ... rest of the examples go here ...

    await db_conn.close()

if __name__ == "__main__":
    asyncio.run(main())
```

Now we can create a couple tables.
We'll be creating an application for an hypothetical library:

```python
    # -- SNIP --
    class Book(Model):
        book_id: Integer = Integer(primary_key=True, unique=True)
        title: Text = Text()
        genre: Text = Text()
        year: Integer = Integer()

    class User(Model):
        user_id: Integer = Integer(primary_key=True, unique=True)
        name: Text = Text(default="John Doe")
        favourite_genre: NullableText = NullableText(default=None)

    # pass the connection to the db to the models
    Book._conn = db_conn
    User._conn = db_conn
```

Let's start by adding some new books:

```python
    # -- SNIP --
    new_books = [
        Book("Automate the Boring Stuff with Python", "Programming", 2019),
        Book("Cosmos", "Astronomy", 1980),
        Book("1984", "Dystopian Fiction", 1949),
    ]

    await Book.insert(*new_books)
```

We want to recommend 10 of the most recent books to the user `john`:

```python
    # -- SNIP --
    recommendations = (
        await Book.select()
        .where(Book.genre == john.favourite_genre)
        .order_by(Book.year, desc=True)
        .limit(10)
    )
```

Jane seems to have changed her taste:

```python
    # -- SNIP --
    jane.favourite_genre = "Fiction"
    await jane.update()
```

The following type hints can be inferred by the type checker:

```python
    # -- SNIP --
    title: str, year: int = await Book.select(Book.title, Book.year)[0]
    books: tuple[Book, ...] = await Book.select()
```

## Docs

For further information, check out [USAGE.md](./docs/USAGE.md).