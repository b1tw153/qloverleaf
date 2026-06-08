# Qloverleaf POC

![Qloverleaf](logo.svg)

## Overpass QL to QLever Interpreter

Qloverleaf is a proof-of-concept interpreter that translates [Overpass QL](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL) queries to
QLever queries, executes the queries at [Qlever](https://qlever.dev), and formats the
results as Overpass GeoJSON or OSM XML output.

## How to Use the Interpreter

Qloverleaf provides the same HTTP query interface as Overpass. You can use a
Qloverleaf server URL anywhere that you would normally use the URL for
Overpass such as Overpass Turbo or JOSM.

### Query Tips

- Single type queries are simpler more likely to run well.
- Bounding boxes and (if: ) filters without other constraints cause QLever to perform
  a full scan of the index - which typically fails by running out of memory or timing
  out. These filters are safe to use when combined with other restrictive filters.
- Use the area filter whenever possible instead of using bbox. The `nwr(area.a)` form
  is exceptionally efficient in QLever -- use it whenever possible!

Some of these issues are mismatches between the QLever and Overpass data models. Other
issues are query composition and optimization challenges that have not yet been
resolved.

## Proof-of-Concept

The current implementation is an incomplete proof-of-concept that demonstrates the
possiblity of adapting Overpass QL queries to a different back end data source.

As a proof-of-concept, the project is not and is not intended to be used for
production use. There are several operational limits to consider when using the
Qloverleaf interpreter:

- The code is not robust and may fail for operational reasons
- The query translations are not optimized - it is relatively easy to write an
  Overpass QL query that the interpreter will translate into a QLever query that will
  fail
- The POC is running on a minimal system with limited processing power and network
  bandwidth
- Complex queries and queries that return large data sets will likely fail due to
  query timeouts or resource limitations
- The POC uses the public QLever server hosted by the University of Freiburg which is
  a shared server with limited resources and which may not be available at some times

## Unimplemented Features

Some aspects of the Overpass QL language have been in the implementation plans but are
not implemented yet:

- [maxsize: ] global setting
- count_tags() evaluator
- count_members() evaluator
- count_distinct_members() evaluator
- count_by_role() evaluator
- count_distinct_by_role() evaluator
- u() evaluator
- min() evalutor
- max() evaluator
- sum() evaluator
- count() evaluator
- foreach statement
- for statement
- complete statement
- if statement
- set.val evaluator
- CSV output
- popup output
- custom output

The unimplemented features are generally "possible" to implement using QLever and the
Qloverleaf interpreter, but simply have not been implemented yet. And the relative
difficulty of implementing these features varies - some are relatively easy, others
are relatively hard.

## Unsupported Features

Some aspects of Overpass QL do not translate well to SPARQL queries or the QLever RDF
schema for OSM. In general, QLever does not have OSM history data, so none of the
Overpass QL operations that rely on attic data can be supported. There is no native
support in QLever for derived or constructed types, nor have these been implemented in
the local query interpreter. Some documented Overpass QL features (e.g., noids) are
broken and the behavior is not reproducible. Individual way vertices are not
addressible in QLever queries.

These features are unsupported with no implementation plans at this time:

- [date: ] global setting - no history data
- [diff: ] global setting - no history data
- [adiff: ] global setting - no history data
- retro statement - no history data
- timeline statement - no history data
- local statement - no history data
- compare statement - no history data
- convert statement - constructed type
- make statement - constructed type
- (bbox) filter in out statement - broken in Overpass
- noids mode in out statement - broken in Overpass
- qt sort in out statment - no quad tile index
- (changed: ) filter - no history data
- (user_touched: ) filter - no history data
- (uid_touched: ) filter - no history data
- (way_link: ) filter - no practical query translation
- keys() evaluator - constructed type
- `::` generic tag evaluator - constructed type
- geom() evaluator - constructed type
- center() evaluator - constructed type
- trace() evaluator - constructed type
- hull() evaluator - constructed type
- pt() evaluator - constructed type
- lstr() evaluator - constructed type
- poly() evaluator - constructed type
- per_member() evaluator - not addressable
- per_vertex() evaluator - not addressable
- pos() evaluator - not addressable
- mtype() evaluator - not addressable
- ref() evaluator - not addressable
- role() evaluator - not addressable
- angle() evaluator - not addressable
- set() evaluator - constructed type
- gcat() evaluator - constructed type
- lrs_in() evaluator - constructed type
- lrs_isect() evaluator - constructed type
- lrs_union() evaluator - constructed type
- lrs_min() evaluator - constructed type
- lrs_max() evaluator - constructed type
- sets containing both NWR elements and AREA elements -- instead of mirroring the
  separate element type for areas that Overpass implements, Qloverleaf uses QLever's
  model where all relations and tagged closed ways are areas

## Known Bugs

- Node coordinates in QLever are rounded to six decimal places instead of retaining
  the original seven decimal places -
  [osm2rdf issue \#135](https://github.com/ad-freiburg/osm2rdf/issues/135)
- [maxsize: ] global setting is not applied
- Output limit restricts the number of rows returned from QLever instead of limiting
  the number of OSM elements returned in the result set
- The way_cnt filter does not work inside a union statement
- Output is sorted by ID in lexical order rather than numerical order
- ... and certainly many more that are unknown

If you find behavior that looks like a bug, please report it as an issue in the
[Qloverleaf project on GitHub](https://github.com/b1tw153/qloverleaf).

## Enhancements

Qloverleaf supports some additional features for debugging and evaluation purposes.

- `[out:raw]` renders the output from QLever as plain text
- `out debug` dumps the state of the selected set and the QLever query that would be
  used to collect data for the output instead of executing the query. This token can
  be combined with other `out` tokens, e.g., `out meta geom debug;`

## Area Handling

Areas are derived data types in both Overpass and QLever and the derivations differ
between the two systems. Overpass includes untagged closed ways in its area derivation
and derives areas as a separate data type. QLever (via `osm2rdf`) does not treat
untagged closed ways as areas, but it assigns area attributes to all relations and
closed tagged ways.

Qloverleaf preserves QLever's area model. Relations and tagged ways can be used
directly in area queries without adaptation. This differs slightly from Overpass,
where ways and relations must be converted to the derived area type before they can be
used in area queries.

## Other Quirks

There are a number of ways in which Qloverleaf behaves differently than Overpass. The
grammar is more strict. The parser performs static typing of set and scalar results.
And in cases where Overpass permits nonsensical query structures, Qloverleaf often
reports errors.

Qloverleaf's warnings and errors are reported the same way that Overpass reports
errors, so you may see them in popups in Overpass Turbo.
