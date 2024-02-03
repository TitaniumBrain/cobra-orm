"""The core of the ORM."""
from __future__ import annotations

from abc import (
    ABCMeta,
    abstractmethod,
)
from enum import Enum
from sqlite3 import Row
from typing import (
    Any,
    ClassVar,
    Generator,
    Generic,
    Iterable,
    Literal,
    NewType,
    Protocol,
    Self,
    TypeVar,
    TypeVarTuple,
    dataclass_transform,
    overload,
)

import aiosqlite as aiosql

from cobra_orm._utils import class_or_instance_method
from cobra_orm.errors import (
    MissingClause,
    MissingColumnValue,
    MultiplePrimaryKeys,
    NoPrimaryKey,
    ORMAPIError,
)

# ===============================================================================
# ===============================================================================
T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)
Ts = TypeVarTuple("Ts")

Success = NewType("Success", bool)
RowCount = NewType("RowCount", int)
ModelT = TypeVar("ModelT", bound="Model")


class Sentinel(Enum):
    MISSING = 0


MISSING = Sentinel.MISSING

SQLParamStmt = tuple[str, dict[str, Any]]
SQLManyParamStmt = tuple[str, list[dict[str, Any]]]


# ===============================================================================
# ===============================================================================
def unique_key(obj: object, label: str) -> str:
    return f"{label}_{id(obj)}"


def row_to_dict(row: Row) -> dict[Any, Any]:
    return dict(zip(row.keys(), row))


def value_to_sql(value: Any | None):
    if value is None:
        return "Null"
    elif isinstance(value, str):
        return f"'{value}'"
    else:
        return f"{value}"


# ===============================================================================
# Columns
# ===============================================================================


class NullableColumn(Protocol[T_co]):
    nullable: ClassVar[Literal[True]]


class Column(Generic[T], metaclass=ABCMeta):
    """Base column class.
    Instances are descriptors meant to be used as members of a Model class."""

    primary_key: bool  # Is the column a primary key
    unique: bool  # Can the column have repeated values
    nullable: ClassVar[Literal[True] | Literal[False]]  # Can the value be NULL (None)
    default: T | None | Literal[Sentinel.MISSING]  # Default value
    name: str  # Internal name
    col_name: str  # Name of the column

    @overload
    def __init__(
        self: NullableColumn[T],
        primary_key: bool = False,
        default: T | None | Literal[MISSING] = MISSING,
        unique: bool = False,
    ) -> None:
        ...

    @overload
    def __init__(
        self,
        primary_key: bool = False,
        default: T | Literal[MISSING] = MISSING,
        unique: bool = False,
    ) -> None:
        ...

    def __init__(
        self,
        primary_key: bool = False,
        default: T | None | Literal[MISSING] = MISSING,
        unique: bool = False,
    ) -> None:
        self.primary_key = primary_key
        self.unique = unique
        self.default = default

    def __set_name__(self, owner: Model, name: str):
        self.name = f"_{name}"
        self.col_name = name

    @overload
    def __get__(self, obj: None, objtype: ModelMeta | None = None) -> Self:
        ...

    @overload
    def __get__(
        self: NullableColumn[T], obj: Model, objtype: ModelMeta | None = None
    ) -> T | None:
        ...

    @overload
    def __get__(self, obj: Model, objtype: ModelMeta | None = None) -> T:
        ...

    def __get__(
        self, obj: Model | None, objtype: ModelMeta | None = None
    ) -> Self | T | None:
        if obj is None:  # called from class
            return self
        return getattr(obj, self.name, self.default)  # type: ignore

    @abstractmethod
    def __set__(self, obj: Model, value: Any):
        return NotImplemented

    def sql(self) -> SQLParamStmt:
        """Column definition."""

        return (
            (
                f'"{self.col_name}" {self.__class__.__name__.upper()}'
                + (" PRIMARY KEY" if self.primary_key else "")
                + (" NOT NULL" if not self.nullable else "")
                + (
                    f" DEFAULT {value_to_sql(self.default)}"
                    if self.default is not MISSING
                    else ""
                )  # Only need to check if it's missing, since __init__ handles None validation
                + (" UNIQUE" if self.unique else "")
            ),
            {},
        )

    def __str__(self) -> str:
        return f"<{self.__class__.__name__} Column {self.col_name}>"

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            + f"primary_key={self.primary_key!r}, "
            + f"nullable={self.nullable!r}, "
            + f"default={self.default!r}, "
            + f"unique={self.unique!r}"
            + ")"
        )

    # WHERE methods
    def __eq__(self, value: T) -> Equal:
        return Equal(self.col_name, value)

    def __ne__(self, value: T) -> NotEqual:
        return NotEqual(self.col_name, value)

    def __lt__(self, value: T) -> LessThan:
        return LessThan(self.col_name, value)

    def __le__(self, value: T) -> LessThanOrEqual:
        return LessThanOrEqual(self.col_name, value)

    def __gt__(self, value: T) -> GreaterThan:
        return GreaterThan(self.col_name, value)

    def __ge__(self, value: T) -> GreaterThanOrEqual:
        return GreaterThanOrEqual(self.col_name, value)

    def like(self, pattern: str) -> Like:
        """
        `%` : any amount of chars

        `_` : one char

        `[abc]` : a, b or c

        `[^abc]` : not a, b nor c

        `[a-c]` : a to c
        """
        return Like(self.col_name, pattern)

    def in_(self, *values: T) -> In:
        return In(self.col_name, values)

    def between(self, lower: T, upper: T) -> Between:
        return Between(self.col_name, lower, upper)

    def null(self) -> Null:
        return Null(self.col_name)

    def not_null(self) -> NotNull:
        return NotNull(self.col_name)


# non null columns ===
class Integer(Column[int]):
    nullable: ClassVar[Literal[False]] = False

    def __set__(self, obj: Model, value: int):
        if isinstance(value, int):
            setattr(obj, self.name, value)
        else:
            raise ValueError(
                "Integer column can only take an int" + f", not {type(value)}"
            )


class Real(Column[float]):
    nullable: ClassVar[Literal[False]] = False

    def __set__(self, obj: Model, value: float):
        if isinstance(value, float):
            setattr(obj, self.name, float(value))
        else:
            raise ValueError(
                "Real column can only take a float" + f", not {type(value)}"
            )


class Text(Column[str]):
    nullable: ClassVar[Literal[False]] = False

    def __set__(self, obj: Model, value: str):
        if isinstance(value, str):
            setattr(obj, self.name, value)
        else:
            raise ValueError("Text column can only take a str" + f", not {type(value)}")


# nullable columns ===
class NullableInteger(Column[int]):
    nullable: ClassVar[Literal[True]] = True

    def __set__(self, obj: Model, value: int | None):
        if isinstance(value, int) or value is None:
            setattr(obj, self.name, value)
        else:
            raise ValueError(
                f"Integer column can only take an int or None, not {type(value)}"
            )


class NullableReal(Column[float]):
    nullable: ClassVar[Literal[True]] = True

    def __set__(self, obj: Model, value: float | None):
        if isinstance(value, float):
            setattr(obj, self.name, float(value))
        elif value is None:
            setattr(obj, self.name, value)
        else:
            raise ValueError(
                f"Real column can only take a float or None, not {type(value)}"
            )


class NullableText(Column[str]):
    nullable: ClassVar[Literal[True]] = True

    def __set__(self, obj: Model, value: str | None):
        if isinstance(value, str) or value is None:
            setattr(obj, self.name, value)
        else:
            raise ValueError(
                f"Text column can only take a str or None, not {type(value)}"
            )


# ===============================================================================
# Tables
# ===============================================================================


class ModelMeta(ABCMeta):
    """Metaclass for a Model."""

    __tablename__: str
    __columns__: dict[str, Column]
    __primary_key_name__: str

    _conn: aiosql.Connection

    def __new__(cls, clsname: str, bases: tuple[type, ...], attrs: dict, **kwargs: Any):
        # Early return to skip initialization for Model, but not its subclasses
        # `bases` is empty for Model
        if not any((isinstance(b, ModelMeta) for b in bases)):
            return super().__new__(cls, clsname, bases, attrs)

        # Inject table name into Model
        tablename = kwargs.pop("name", clsname)
        attrs["__tablename__"] = tablename

        # Validate table structure and inject __columns__ into Model
        columns: dict[str, Column] = {}
        for key, value in attrs.items():
            if isinstance(value, Column):
                columns[key] = value
        attrs["__columns__"] = columns

        # Check for only one primary key
        p_keys = tuple((k, v) for k, v in columns.items() if v.primary_key)
        match p_keys:
            case []:
                raise NoPrimaryKey
            case [p_key]:
                attrs["__primary_key_name__"] = p_key[0]
            case [*_]:
                raise MultiplePrimaryKeys

        return super().__new__(cls, clsname, bases, attrs)

    def __str__(self) -> str:
        return f"<{self.__class__.__qualname__} columns=[{', '.join(c for c in self.__columns__.keys())}] primary_key={self.__primary_key__.col_name}>"

    @property
    def __primary_key__(self):
        return self.__columns__[self.__primary_key_name__]


@dataclass_transform(
    kw_only_default=True,
    field_specifiers=(Text, Integer, Real, NullableText, NullableInteger, NullableReal),
)
class Model(metaclass=ModelMeta):
    """Base model class. All models inherit from it.
    The class object represents a table.
    An instance represents a row from the table."""

    __tablename__: str
    __columns__: dict[str, Column]

    _conn: aiosql.Connection

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def __primary_key__(self):
        return getattr(self, self.__class__.__primary_key_name__)

    def __str__(self) -> str:
        return (
            f"{self.__class__.__name__} row <"
            + ", ".join(
                f"{self.__class__.__columns__[k].col_name}: {getattr(self, k)}"
                for k in self.__columns__.keys()
            )
            + ">"
        )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            + ", ".join(
                f"{self.__class__.__columns__[k].col_name}={self.__columns__[k]!r}"
                for k in self.__columns__.keys()
            )
            + ")"
        )

    @overload
    @classmethod
    def select(cls, *, distinct: bool = False) -> SelectStmt[Self, Self]:
        ...

    @overload
    @classmethod
    def select(
        cls, *columns: *Ts, distinct: bool = False
    ) -> SelectStmt[Self, tuple[*Ts]]:
        ...

    @classmethod
    def select(
        cls, *columns: *Ts, distinct: bool = False
    ) -> SelectStmt[Self, Self] | SelectStmt[Self, tuple[*Ts]]:
        return SelectStmt(cls, *columns, distinct=distinct)

    @class_or_instance_method
    def insert(cls_or_self: Model | ModelMeta, *rows: Model) -> InsertStmt:
        if isinstance(cls_or_self, ModelMeta):  # called from class
            if len(rows) > 0:
                return InsertStmt(cls_or_self, *rows)
            raise ORMAPIError(
                f"Table: {cls_or_self.__name__} - Must pass one or more row instances."
            )
        else:  # called from instance
            return InsertStmt(type(cls_or_self), cls_or_self)

    @class_or_instance_method
    def update(
        cls_or_self: Model | ModelMeta, fake_row: Model | None = None
    ) -> UpdateStmt:
        if isinstance(cls_or_self, ModelMeta):  # called from class
            if fake_row is not None:  # must pass a row
                return UpdateStmt(cls_or_self, fake_row, True)
            else:
                raise ORMAPIError(
                    "A (partially) defined Model instance must be passed when calling 'update' as a classmethod."
                )
        else:  # called from instance
            return UpdateStmt(type(cls_or_self), cls_or_self)

    @class_or_instance_method
    def delete(cls_or_self: Model | ModelMeta) -> DeleteStmt:
        if isinstance(cls_or_self, ModelMeta):  # called from class
            return DeleteStmt(cls_or_self)
        else:  # called from instance
            return DeleteStmt(type(cls_or_self), cls_or_self)

    @classmethod
    def create(cls) -> CreateStmt:
        """Create the table."""
        return CreateStmt(cls)

    @classmethod
    def drop(cls) -> DropStmt:
        """Drop the table."""
        return DropStmt(cls)

    def __hash__(self) -> int:
        return hash((getattr(self, c) for c in self.__columns__.keys()))

    def __eq__(self, other: Self) -> bool:
        if not isinstance(other, type(self)):
            return False
        return hash(self) == hash(other)


# ===============================================================================
# Clauses
# ===============================================================================


class WhereClause:
    _cond: SQLCondition | SQLConditionalOperator

    def __init__(
        self,
        *conditions: SQLCondition | SQLConditionalOperator,
    ) -> None:
        if SQLConditionalOperator.is_one(*conditions):
            self._cond = conditions[0]
        else:
            self._cond = And(*conditions)

    def sql(self) -> SQLParamStmt:
        cond_sql, cond_params = self._cond.sql()
        return (f" WHERE {cond_sql}", cond_params)

    def __str__(self) -> str:
        return f"<SQL Condition: Where ...>"

    def __repr__(self) -> str:
        return f"WhereClause({self._cond!r})"


class Whereable(Protocol):
    _where: WhereClause | None


W = TypeVar("W", bound=Whereable)


class WhereMixin:
    def __init__(self: Whereable) -> None:
        self._where = None

    def where(self: W, *conditions: SQLCondition | SQLConditionalOperator) -> W:
        self._where = WhereClause(*conditions)
        return self


# ===============================================================================
# Conditions
# ===============================================================================
class SQLCondition(metaclass=ABCMeta):
    _where: WhereClause | None = None

    @abstractmethod
    def sql(self) -> SQLParamStmt:
        return NotImplemented

    @abstractmethod
    def __str__(self) -> str:
        return NotImplemented

    @abstractmethod
    def __repr__(self) -> str:
        return NotImplemented


class SQLComparison(SQLCondition):
    """Implements logic for all comparison operations.
    Subclasses need to define their operator via the `__operator__` class var.
    """

    __operator__: str
    _col_name: str
    _value: Any

    def __init__(self, col_name: str, value: Any) -> None:
        self._col_name = col_name
        self._value = value

    def sql(self) -> SQLParamStmt:
        k = unique_key(self, "comp_value")
        params = {k: self._value}

        return (f"{self._col_name} {self.__operator__} :{k}", params)

    def __str__(self) -> str:
        return f"<SQL Condition: '{self._col_name}' {self.__operator__} {self._value}>"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._col_name!r}, {self._value!r})"


class Equal(SQLComparison):
    __operator__ = "="


class NotEqual(SQLComparison):
    __operator__ = "!="


class LessThan(SQLComparison):
    __operator__ = "<"


class LessThanOrEqual(SQLComparison):
    __operator__ = "<="


class GreaterThan(SQLComparison):
    __operator__ = ">"


class GreaterThanOrEqual(SQLComparison):
    __operator__ = ">="


class Like(SQLCondition):
    def __init__(self, col_name: str, pattern: str) -> None:
        self._col_name = col_name
        self._pattern = pattern

    def sql(self) -> SQLParamStmt:
        k = unique_key(self, "pattern")
        params = {k: self._pattern}

        return (f"{self._col_name} LIKE :{k}", params)

    def __str__(self) -> str:
        return f"<SQL Condition: '{self._col_name}' Like {self._pattern}>"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._col_name!r}, {self._pattern!r})"


class In(SQLCondition):
    def __init__(self, col_name: str, *values: Any) -> None:
        self._col_name = col_name
        self._values = values

    def sql(self) -> SQLParamStmt:
        params = {unique_key(self, "in_value"): v for v in self._values}

        return (
            f"{self._col_name} IN ({', '.join(f':{k}' for k in params.keys())})",
            params,
        )

    def __str__(self) -> str:
        return f"<SQL Condition: '{self._col_name}' In {self._values}>"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._col_name}, {', '.join(map(repr, self._values))})"


class Between(SQLCondition):
    def __init__(self, col_name: str, lower: Any, upper: Any) -> None:
        self._col_name = col_name
        self._lower = lower
        self._upper = upper

    def sql(self) -> SQLParamStmt:
        k_l = unique_key(self, "lower")
        k_u = unique_key(self, "upper")
        params = {k_l: self._lower, k_u: self._upper}

        return (f"{self._col_name} BETWEEN {k_l} AND {k_u}", params)

    def __str__(self) -> str:
        return f"<SQL Condition: '{self._col_name}' Between [{self._lower}, {self._upper}]>"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._col_name}, {self._lower!r}, {self._upper!r})"


class Null(SQLCondition):
    def __init__(self, col_name: str) -> None:
        self._col_name = col_name

    def sql(self) -> SQLParamStmt:
        return (f"{self._col_name} IS NULL", {})

    def __str__(self) -> str:
        return f"<SQL Condition: '{self._col_name}' Null>"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._col_name!r})"


class NotNull(SQLCondition):
    def __init__(self, col_name: str) -> None:
        self._col_name = col_name

    def sql(self) -> SQLParamStmt:
        return (f"{self._col_name} IS NOT NULL", {})

    def __str__(self) -> str:
        return f"<SQL Condition: '{self._col_name}' Not Null>"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._col_name!r})"


# ===============================================================================
# Conditional Operators
# ===============================================================================
class SQLConditionalOperator(metaclass=ABCMeta):
    @classmethod
    def is_one(cls, *conditions: SQLCondition | SQLConditionalOperator) -> bool:
        return len(conditions) == 1 and isinstance(
            conditions[0], SQLConditionalOperator
        )

    @abstractmethod
    def sql(self) -> SQLParamStmt:
        return NotImplemented

    @abstractmethod
    def __str__(self) -> str:
        return NotImplemented

    @abstractmethod
    def __repr__(self) -> str:
        return NotImplemented


class Not(SQLConditionalOperator):
    _cond: SQLCondition | SQLConditionalOperator

    def __init__(self, *conditions: SQLCondition | SQLConditionalOperator) -> None:
        if super().is_one(*conditions):
            self._cond = conditions[0]
        else:
            self._cond = And(*conditions)

    def sql(self) -> SQLParamStmt:
        cond_sql, cond_params = self._cond.sql()

        return (f"NOT {cond_sql}", cond_params)

    def __str__(self) -> str:
        return f"<SQL Condition: Not {self._cond}>"

    def __repr__(self) -> str:
        return f"Not({self._cond!r})"


class And(SQLConditionalOperator):
    _conds: tuple[SQLCondition | SQLConditionalOperator, ...]

    def __init__(self, *conditions: SQLCondition | SQLConditionalOperator) -> None:
        if super().is_one(*conditions) and isinstance(conditions[0], And):
            self._conds = conditions[0]._conds
        else:
            self._conds = conditions

    def sql(self) -> SQLParamStmt:
        sqls = []
        params = {}

        for c in self._conds:
            cond_sql, cond_params = c.sql()
            sqls.append(cond_sql)
            params.update(cond_params)

        return (f"({' AND '.join(sqls)})", params)

    def __str__(self) -> str:
        return f"<SQL Condition: And [{self._conds}]>"

    def __repr__(self) -> str:
        return f"And({', '.join(map(repr, self._conds))})"


class Or(SQLConditionalOperator):
    _conds: tuple[SQLCondition | SQLConditionalOperator, ...]

    def __init__(self, *conditions: SQLCondition | SQLConditionalOperator) -> None:
        if super().is_one(*conditions) and isinstance(conditions[0], Or):
            self._conds = conditions[0]._conds
        else:
            self._conds = conditions

    def sql(self) -> SQLParamStmt:
        sqls = []
        params = {}

        for c in self._conds:
            cond_sql, cond_params = c.sql()
            sqls.append(cond_sql)
            params.update(cond_params)

        return (f"({' OR '.join(sqls)})", params)

    def __str__(self) -> str:
        return f"<SQL Condition: Or [{self._conds}]>"

    def __repr__(self) -> str:
        return f"Or({', '.join(map(repr, self._conds))})"


# ===============================================================================
# Statements
# ===============================================================================


class SQLStatement(Generic[T], metaclass=ABCMeta):
    _table: ModelMeta

    def __init__(self) -> None:
        pass

    @abstractmethod
    def sql(self) -> SQLParamStmt:
        """Compute and return the SQL string and parameters for the associated command."""
        return NotImplemented

    def __str__(self) -> str:
        return f"..."

    @abstractmethod
    def __repr__(self) -> str:
        pass

    def __await__(self) -> Generator[Any, None, T]:
        return self._execute().__await__()

    @abstractmethod
    async def _execute(self) -> T:
        """Execute the query.

        If a SELECT, return the corresponding rows.
        If a INSERT, UPDATE, DELETE, return number of affected rows.
        If DROP, CREATE, return True if successful, False if not.
        """
        return NotImplemented


class SelectStmt(
    Generic[ModelT, T], WhereMixin, SQLStatement[Iterable[Row] | tuple[Model, ...]]
):
    _table: type[ModelT]
    _cols: tuple[Column[Any], ...]
    _order_by: list[tuple[Column, bool]]  # list of (col, desc)
    _limit: int | None
    _distinct: bool

    @overload
    def __init__(
        self: SelectStmt[ModelT, ModelT],
        table: type[ModelT],
        *,
        distinct: bool = False,
    ) -> None:
        ...

    @overload
    def __init__(
        self: SelectStmt[ModelT, tuple[*Ts]],
        table: type[ModelT],
        *columns: *Ts,
        distinct: bool = False,
    ) -> None:
        ...

    def __init__(
        self, table: type[ModelT], *columns: Column[Any], distinct: bool = False
    ) -> None:
        self._table = table
        self._cols = columns
        self._distinct = distinct
        self._order_by = []
        self._limit = None

        super().__init__()

    def sql(self) -> SQLParamStmt:
        params = {}
        sql = (
            "SELECT "
            + ("DISTINCT " if self._distinct else "")
            + (
                ", ".join(c.col_name for c in self._cols)
                if len(self._cols) > 0
                else "*"
            )
            + f" FROM {self._table.__tablename__} "
        )
        if self._where:
            where_sql, where_params = self._where.sql()
            sql += where_sql
            params.update(where_params)
        sql += (
            (
                f"ORDER BY {', '.join((o[0].col_name + ('DESC' if o[1] else '')) for o in self._order_by)} "
                if len(self._order_by) > 0
                else ""
            )
            + (f"LIMIT {self._limit}" if self._limit else "")
            + ";"
        )
        return sql, params

    def __str__(self) -> str:
        return f"<Statement: Select from table {self._table.__tablename__}>"

    def __repr__(self) -> str:
        return (
            f"SelectStmt({self._table!r}, "
            + ((", ".join(map(repr, self._cols)) + ", ") if self._cols else "")
            + f"distinct={self._distinct!r})"
            + "".join(
                f".order_by({o[0].col_name!r}, desc={o[1]!r})" for o in self._order_by
            )
            + (f".limit({self._limit!r})" if self._limit else "")
        )

    @overload
    def __await__(
        self: SelectStmt[ModelT, ModelT],
    ) -> Generator[Any, None, tuple[ModelT, ...]]:
        ...

    @overload
    def __await__(
        self: SelectStmt[ModelT, tuple[*Ts]]
    ) -> Generator[Any, None, tuple[tuple[*Ts], ...]]:
        ...

    def __await__(
        self: SelectStmt[ModelT, ModelT] | SelectStmt[ModelT, tuple[*Ts]]
    ) -> Generator[Any, None, tuple[ModelT, ...] | tuple[tuple[*Ts], ...]]:
        return self._execute().__await__()

    @overload
    async def _execute(self: SelectStmt[ModelT, ModelT]) -> tuple[ModelT, ...]:
        ...

    @overload
    async def _execute(self: SelectStmt[ModelT, tuple[*Ts]]) -> tuple[tuple[*Ts], ...]:
        ...

    async def _execute(
        self: SelectStmt[ModelT, ModelT] | SelectStmt[ModelT, tuple[*Ts]]
    ) -> tuple[ModelT, ...] | tuple[tuple[*Ts], ...]:
        cursor = await self._table._conn.execute(*self.sql())
        rows = await cursor.fetchall()
        if len(self._cols) > 0:
            return tuple(map(tuple, rows))  # type: ignore
        else:
            return tuple(self._table(**row_to_dict(row)) for row in rows)  # type: ignore

    def order_by(self, *columns: Column, desc: bool = False) -> Self:
        self._order_by.extend((col, desc) for col in columns)
        return self

    def limit(self, n: int) -> Self:
        self._limit = n
        return self


class InsertStmt(SQLStatement[RowCount]):
    _rows: tuple[Model, ...]

    def __init__(self, table: ModelMeta, *rows: Model) -> None:
        self._table = table
        self._rows = rows

        super().__init__()

    def sql(self) -> SQLManyParamStmt:
        u_keys: dict[str, str] = {}  # col name to unique key
        cols_list: list[dict[str, Any]] = []  # list of dict of unique key to col value

        for col_name in self._rows[0].__columns__.keys():
            u_keys[col_name] = f"{col_name}_insert_value"

        for row in self._rows:
            cols: dict[str, Any] = {}
            for col_name, col in row.__columns__.items():
                col_val = getattr(row, col_name)
                if col_val is MISSING:
                    if col.default is MISSING:
                        raise MissingColumnValue
                    col_val = col.default

                cols[u_keys[col_name]] = col_val
            cols_list.append(cols)

        sql = f"INSERT INTO {self._table.__tablename__} ({', '.join(f'{k}' for k in u_keys.keys())}) VALUES ({', '.join(f':{k}' for k in u_keys.values())})"
        params = cols_list

        return sql, params

    def __str__(self) -> str:
        return f"<Statement: Insert into table {self._table.__tablename__}>"

    def __repr__(self) -> str:
        return (
            f"InsertStmt(table={self._table.__name__}" + f", row={self._rows!r}"
            if self._rows
            else "" + ")"
        )

    async def _execute(self) -> RowCount:
        cursor = await self._table._conn.executemany(*self.sql())
        await self._table._conn.commit()
        return RowCount(cursor.rowcount)


class UpdateStmt(WhereMixin, SQLStatement[RowCount]):
    _row: Model
    _fake_row: bool

    def __init__(self, table: ModelMeta, row: Model, fake_row: bool = False) -> None:
        """
        Parameters
        ----------
        table : ModelMeta
            The SQL table.
        row : Model
            The row with the `Column`s to update.
            `MISSING` column value means not to update that column.
        fake_row : bool, optional
            If True, `row` is just a possibly incomplete `Model` instance, defining the columns to update.
            If False (default), `row` is the row that should be updated, using it's primary key.
        """
        self._table = table
        self._row = row
        self._fake_row = fake_row

        super().__init__()

    def sql(self) -> SQLParamStmt:
        sql = f"UPDATE {self._table.__tablename__}"
        params: dict[str, Any] = {}
        # set values ===
        u_keys: dict[str, str] = {}  # col name to unique key
        cols: dict[str, Any] = {}  # unique key to col value

        for col_name, col in self._row.__columns__.items():
            col_val = getattr(self._row, col_name)
            if col_val is MISSING:
                continue

            u_keys[col_name] = (u_key := unique_key(col_val, "insert_value"))
            cols[u_key] = col_val

        params.update(cols)

        sql += " SET " + ", ".join(
            f"{col_name} = :{u_key}" for col_name, u_key in u_keys.items()
        )

        # where ===
        if self._fake_row:  # called on class
            if self._where is not None:
                where_sql, where_params = self._where.sql()
                sql += where_sql
                params.update(where_params)
            else:
                raise MissingClause(
                    f"Update statement on table {self._table.__tablename__} would affect all rows."
                )
        else:  # called on row
            sql += f" WHERE {Column, self._table.__primary_key__.col_name} = :p_key"
            params["p_key"] = self._row.__primary_key__
        return f"{sql};", params

    def __str__(self) -> str:
        return f"<Statement: Update in table {self._table.__tablename__}>"

    def __repr__(self) -> str:
        return (
            f"UpdateStmt(table={self._table.__name__}"
            + (f", row={self._row!r}" if self._row else "")
            + (f"fake_row={self._fake_row!r}")
            + ")"
        )

    async def _execute(self) -> RowCount:
        cursor = await self._table._conn.execute(*self.sql())
        await self._table._conn.commit()
        return RowCount(cursor.rowcount)


class DeleteStmt(WhereMixin, SQLStatement[RowCount]):
    _row: Model | None

    def __init__(self, table: ModelMeta, row: Model | None = None) -> None:
        self._table = table
        self._row = row

        super().__init__()

    def sql(self) -> SQLParamStmt:
        sql = f"DELETE FROM {self._table.__tablename__}"
        params: dict[str, Any] = {}

        if self._row is not None:  # called on row
            sql += f" WHERE {Column, self._table.__primary_key__.col_name} = :p_key"
            params["p_key"] = self._row.__primary_key__
        elif self._where is not None:
            where_sql, where_params = self._where.sql()
            sql += where_sql
            params.update(where_params)
        else:
            raise MissingClause(
                f"Delete statement on table {self._table.__tablename__} would delete all rows."
            )
        return (f"{sql};", params)

    def __str__(self) -> str:
        return f"<Statement: Delete from table {self._table.__tablename__}>"

    def __repr__(self) -> str:
        return (
            f"DeleteStmt(table={self._table.__name__}"
            + (f", row={self._row!r}" if self._row else "")
            + ")"
        )

    async def _execute(self) -> RowCount:
        cursor = await self._table._conn.execute(*self.sql())
        await self._table._conn.commit()
        return RowCount(cursor.rowcount)


class CreateStmt(SQLStatement[Success]):
    def __init__(self, table: ModelMeta) -> None:
        self._table = table

        super().__init__()

    def sql(self) -> SQLParamStmt:
        stmt = f"CREATE TABLE IF NOT EXISTS {self._table.__tablename__}"
        params = {}

        col_sqls = []
        for c in self._table.__columns__.values():
            sql, col_params = c.sql()
            col_sqls.append(sql)
            params.update(col_params)

        return (f"{stmt} ({', '.join(col_sqls)})", params)

    def __str__(self) -> str:
        return f"<Statement: Create table {self._table.__tablename__}>"

    def __repr__(self) -> str:
        return f"CreateStmt(table={self._table.__name__})"

    async def _execute(self) -> Success:
        await self._table._conn.execute(*self.sql())
        async with self._table._conn.execute(
            f"SELECT name FROM sqlite_master WHERE name=?", (self._table.__tablename__,)
        ) as cursor:
            # Return True is successful, False otherwise
            success = Success(await cursor.fetchone() is not None)
        return success


class DropStmt(SQLStatement[Success]):
    def __init__(self, table: ModelMeta) -> None:
        self._table = table

        super().__init__()

    def sql(self) -> SQLParamStmt:
        return f"DROP TABLE {self._table.__tablename__};", {}

    def __str__(self) -> str:
        return f"<Statement: Drop table {self._table.__tablename__}>"

    def __repr__(self) -> str:
        return f"DropStmt(table={self._table.__name__})"

    async def _execute(self) -> Success:
        await self._table._conn.execute(*self.sql())
        await self._table._conn.commit()
        async with self._table._conn.execute(
            f"SELECT name FROM sqlite_master WHERE name=?", (self._table.__tablename__,)
        ) as cursor:
            # Return True is successful, False otherwise
            return Success(await cursor.fetchone() is None)
