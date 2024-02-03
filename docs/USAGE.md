# Usage

Cobra ORM is an async ORM for aiosqlite, so we'll define an asynchronous function for example purposes.

```python
import asyncio
from cobra_orm import *

async def main():

    # -- examples go here --

asyncio.run(main())
```

## Defining tables

Tables are defined by a class that inherits from `cobra_orm.Model`.
You can optionally pass in a name for the table, otherwise the class name is used:

```python
    class MyTable(Model, name="Table"):
        pass
```

Table columns can be one of `Integer`, `Text`, `Real` or a nullable version of these:
For proper typing, you must include the type hints:

```python
    class MyTable(Model, name="Table"):
        foo: Integer = Integer(primary_key=True, unique=True)
        bar: Text = Text(default="example")
        baz: Real = Real(default=1.0)
        spam: Integer = NullableInteger(default=None)
```

## Database connection

Before you can manipulate a database, you must first pass a connection to it to the Model subclasses:

```python

    connection = await aiosqlite.connect("path/to/database")

    MyTable._conn = connection

```

## Creating tables

Creating a table is as easy as calling the `Model.create` method.
This method returns the success value:

```python
    success: bool = await MyTable.create()
    if success:
        print("Table was created!")

```

## Dropping tables

Make Little Bobby Tables proud with a call to `Model.drop`.
This alaso returns the operation's success value:

```python
    await MyTable.drop()
```

## Inserting rows

`Model` subclass instances represent rows of a table.
You can create them manually. Columns with default values can be ommitted:

```python
    my_rows: list[MyTable] = [
        MyTable(foo=1234, bar="qwerty"),
        MyTable(foo=5678),
    ]
```

You can insert rows by calling `Model.insert` on either the rows or the table:

```python
    for row in my_rows:
        await row.insert()

    # OR

    await MyTable.insert(*my_rows)
```

## Selecting rows

A simple call to `Model.select` selects all rows:

```python
    all_rows: tuple[MyTable, ...] = await MyTable.select()
```

Instead of selecting full rows, you can select only the columns you want:

```python
    all_rows: tuple[tuple[int, int | None], ...] = await MyTable.select(MyTable.foo, MyTable.spam)
```

You can select rows depending on a WHERE clause:

```python
    some_rows: tuple[MyTable, ...] = await MyTable.select().where(...)
```

More information on [WHERE clauses](#where-clauses) can be found below.

You can specify how many rows should be returned at most:

```python
    some_rows: tuple[MyTable, ...] = await MyTable.select().limit(10)
```

You can also choose how to the rows:

```python
    some_rows: tuple[MyTable, ...] = await MyTable.select().order_by(MyTable.bar)

    # for more control, you can chain multiple calls to
    # order_by and specify the desc flag

    some_rows: tuple[MyTable, ...] = (
        await MyTable.select()
        .order_by(MyTable.bar)
        .order_by(MyTable.foo, MyTable.spam, desc=True)
    )
```

## Updating rows

If you have a row object, you can change its values and call its `update` method directly.
This will update the correct row by using its primary key, so one must be defined for this to work. 

```python
    row: MyTable = ...
    row.baz += 1

    await row.update()
```

Alternatively, you can update one or more rows that meet a certain condition by calling the method on the class and using a WHERE clause:

```python
    await row.update(MyTable(bar="new_value")).where(...)
```

## Deleting rows

You can call the `delete` method on a row to delete it.
This will delete the correct row by using its primary key, so one must be defined for this to work. 

```python
    row: MyTable = ...

    await row.delete()
```

Alternatively, you can delete all rows that meet a certain condition by calling the method on the class and using a WHERE clause:

```python
    await MyTable.delete().where(...)
```

## Where clauses

WHERE clauses can be used to specify a condition in a SELECT, UPDATE or DELETE statement.

### Simple conditions

You can use the `==`, `!=`, `<`, `<=`, `>` and `>=` comparison operators on a column:

```python
    await MyTable.select().where(MyTable.baz > 2.0)
```

Use `like` to test a column against a specific pattern (refer to the docstring or the sqlite docs for the available syntax):

```python
    await MyTable.select().where(MyTable.bar.like("%abc%"))
```

Check if a column is one of a set of values:

```python
    await MyTable.select().where(MyTable.spam.in_(1, 4, 8))
```

Check if a value is contained in a range:

```python
    await MyTable.select().where(MyTable.bar.between(2, 4))
```

Check if a value is null or not:

```python
    await MyTable.select().where(MyTable.spam.null())
    await MyTable.select().where(MyTable.spam.not_null())
```

### Compound conditions

You can combine multiple conditions with `And` and `Or` to create more complex ones:


```python
    # In this example, we'll only select rows where either:
    #  - spam is not null and bar is greater than 3
    #  OR
    #  - spam is null
    await MyTable.select().where(
        Or(
            And(
                MyTable.spam.not_null(),
                MyTable.bar > 3,
            ),
            MyTable.spam.null(),
        )
    )
```

## More on Model instances

Model instances (rows) can be compared to each other.
They'll be considered equal if all their columns have the same value.

They are also hashable, which means they can be used as dictionary keys.
*However*, since they are mutable, this is not advised.