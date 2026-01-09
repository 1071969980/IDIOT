## MSON Cheatsheet

This cheatsheet is an example orientated document showing some MSON features in
the context of API Blueprint. Refer to the [MSON\\
Specification](https://apiblueprint.org/documentation/mson/specification.html) for detailed
documentation on MSON.

## Core Syntax[\#](https://apiblueprint.org/documentation/mson/cheatsheet.html\#core-syntax "Permanent Link")

Declaring an [API Blueprint\\
Action](https://apiblueprint.org/documentation/specification.html#def-action-section) describing how
`GET` requests to `/files` may look in an API. The API Blueprint describes that
the API may return a 200 response using JSON (with the `application/json`
content type). It may return an array which can only contain objects which must
have the key `path`.

```
# GET /files

+ Response 200 (application/json)
    + Attributes (array, fixed-type)
        + (object)
            + path: `/files` (required)
```

### Declaring Types[\#](https://apiblueprint.org/documentation/mson/cheatsheet.html\#declaring-types "Permanent Link")

MSON allows declaring types to allow reusable structures and to keep API
Blueprint's short and simple. Reusable data structures sit under the `Data
Structures` heading.

```
# My API

## GET /files

+ Response 200 (application/json)
    + Attributes (array[File], fixed-type)

## Data Structures

### File (object)

+ name: `index.html`
+ size: 5012 (number)
+ `created_at`: `2007-04-05T24:00` (string)
+ permissions (Permission)

### Permission (enum)

+ r (default) - Read only
+ rw - Read-write
```

**NOTE**: _It's important to note, that if a key or value contains reserved_
_characters such as `:`, `(`,`)`, `<`, `>`, `{`, `}`, `[`, `]`, `_`,_
_`&ast;`, `-`, `+`, ````` then the value must be wrapped in a_
_code-block using back-ticks._

## Types[\#](https://apiblueprint.org/documentation/mson/cheatsheet.html\#types "Permanent Link")

### Objects[\#](https://apiblueprint.org/documentation/mson/cheatsheet.html\#objects "Permanent Link")

Objects consist of key-value pairs. Properties are optional by default. Values
of properties are string by default.

```
+ name: API Blueprint (required)
```

An object consisting of a date property which must be present, but may be `null`:

```
+ date (required, nullable)
```

The fixed keyword can be used to declare that the value must be present with
as-is, for example the following declares a member `type` which if present must
have the value `admin`.

```
+ type: admin (fixed)
```

#### One Of[\#](https://apiblueprint.org/documentation/mson/cheatsheet.html\#one-of "Permanent Link")

`One Of` can be used to describe mutually exclusive sets of members. For example,
User type must contain the `name` property, and must contain either an `id`, or a
`username` property.

```
## User (object)

+ name: Kyle (required)
+ One Of
    + username: kylef (required)
    + id: 1 (number, required)
```

See the [enum type](https://apiblueprint.org/documentation/mson/cheatsheet.html#enumerations) for declaring a mutally exclusive set of
types or values.

### Arrays[\#](https://apiblueprint.org/documentation/mson/cheatsheet.html\#arrays "Permanent Link")

Declaring an array which may only contain strings or numbers (array of a `fixed-type`, `string` or `number`):

```
+ Attributes (array[string, number], fixed-type)
```

With example values, and descriptions:

```
+ Attributes (array, fixed-type)
    + 10 GBP
    + 20 GBP
    + 12.99 (number)
```

Declaring an array which may only contain the specified object which requires a
`name` property:

```
+ Attributes (array, fixed-type)
    + (object)
        + name (required)
```

### Enumerations[\#](https://apiblueprint.org/documentation/mson/cheatsheet.html\#enumerations "Permanent Link")

The `enum` type can be used to describe an exclusive list of possible values or types.

Declaring an enumeration which may only contain one of the permitted values
(`north`, `east`, `south`, `west`):

```
## Direction (enum)

+ north
+ east
+ south
+ west
```

Declaring an enumeration where any value is permitted providing the value is a
`string` or a `number`:

```
## Data Structures

### StringOrNumber (enum[string, number])

## GET /products

+ Response 200 (application/json)
    + Attributes (array, fixed-type)
        + (object)
            + name: API Blueprint
            + price: 2.99 (StringOrNumber) - Price to purchase the product, as a string or a number
            + state (enum)
                + `in stock` (default)
                + `sold-out`
```

### Primitive Types[\#](https://apiblueprint.org/documentation/mson/cheatsheet.html\#primitive-types "Permanent Link")

The primitive types `string`, `number`, and `boolean` may be used.

```
## Example Object

+ name (string)
+ `is_admin` (boolean)
+ age (number)
+ extra (array)
    + hello world
    + 2 (number)
    + true (boolean)
```