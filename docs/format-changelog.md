# Format changelog

Changes of the map format by mapcan version. All of them keep `mapcan: 1`: see
[Versioning and compatibility](format.md#versioning-and-compatibility). A map that uses a field
needs at least the version of mapcan that introduced it; former names stay readable.

## 0.21

- The frame field `dlc` is now `length` (data length in bytes). On CAN FD and with the J1939
  transport protocol the length is not a DLC code; the code follows from it. `dlc` is still read
  with a `deprecated-key` warning. Generated code: `<FRAME>_LENGTH` (C) and `LENGTH` (Python);
  `<FRAME>_DLC` / `DLC` remain as deprecated aliases.
- The signal fields `signed` and `signed_code` are one field, `representation`: `unsigned`
  (default), `twos_complement`, `ones_complement` or `sign_magnitude`; `signed: true` alone is
  `twos_complement`. An SDO value's `signed: true` is `representation: twos_complement`.
- `mapcan migrate` rewrites former field names; the rule `deprecated-key` reports them.
