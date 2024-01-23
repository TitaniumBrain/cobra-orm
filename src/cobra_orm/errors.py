"""Exceptions related to the ORM."""

# ===============================================================================
# ===============================================================================


class ORMException(Exception):
    """Base exception for all exceptions from the ORM."""

    pass


class NoPrimaryKey(ORMException):
    """Table definition doesn't declare a primary key."""

    pass


class MultiplePrimaryKeys(ORMException):
    """Table definition declares more than one primary key."""

    pass


class NoConnection(ORMException):
    """Table definition doesn't have a database connection."""

    pass


class ORMAPIError(ORMException):
    """Invalid invocation of ORM method."""

    pass


class MissingColumnValue(ORMException):
    """Row is missing a value which doesn't have a default."""

    pass


class MissingClause(ORMException):
    """Statement doesn't have a WHERE clause, all rows would be affected."""

    pass
