# The map in Plan a flight

Choose **Draw it on a map** in "1. The survey area".

## Drawing

The toolbar at the top left of the map has polygon, rectangle, circle, line and a pin (takeoff point).
Each shape appears in the list under the map with a role you can change:

| Role | Meaning |
|---|---|
| Map inside it | photograph this area |
| Leave it out | a hole inside a mapped area (a lake, a building); a shape drawn inside another starts as this |
| Map a band around it (outside) | a ring of the chosen width around the shape: "map the outside of the polygon" |
| Map a strip along it | for a line: a strip of the chosen width (a road, a river, a power line) |

The area that will be planned is drawn in green. "Leave it out" means *not planned for coverage*: the aircraft may still fly over that part to turn or
to reach the next line, so it is not a no-fly zone.

## Fixing a mistake

- **Undo** (under the map) takes back one change at a time: a drawing, a role, a width, a delete, an edit,
  the takeoff pin, even *Remove all shapes*. Typing a width digit by digit counts as one step.
- **Edit** (the pencil in a shape's row) lets you move its corners: numbered discs appear on the map;
  press the number of a corner, then **click on the map where it should go**. *Add a corner* puts a new one
  in the middle of the longest side (and picks it, ready to move); *Remove the picked corner* takes one
  away (an area keeps at least three, a line two). For a circle you pick its centre and click, and type
  the radius. A rectangle whose corner moves becomes a polygon, since its corners are no longer square.
  A move that would make the outline cross itself is refused, and the shape stays as it was.
- *Delete* (the bin) removes a shape; *Remove all shapes* clears the map.
- Leaflet's own edit button is hidden: it works on shapes the browser keeps, and here Avispria keeps them.

## Finding the place

- **Search**: type a place name and press Search, or type `latitude, longitude` to go straight there (no
  search is made for coordinates).
- **My location**: asks the browser where this computer is, and shows it with its accuracy. A computer
  usually knows its position only roughly (from its network), often to within a kilometre; the page says so
  when it is that rough. When it is accurate to 100 m or better you can use it as the takeoff point.
  Browsers allow this only on pages whose address starts with `http://127.0.0.1` or `http://localhost`
  (the way Avispria starts), and ask your permission first.

## What goes over the internet, and only when you ask

| Action | What is sent, to whom |
|---|---|
| Show map background (a switch, off by default) | the map pictures needed, from OpenStreetMap's tile server (or the address you give) |
| Search | the words you typed, to the place-search service (OpenStreetMap's Nominatim, or the address you give) |
| My location | nothing from Avispria; the browser may ask its own location service |

Nothing else leaves this computer, and everything works without the internet except these.

## The services' rules, and how Avispria keeps to them

OpenStreetMap's public servers are free and shared. Their policies ask for a visible credit (shown),
an application name in each request (`Avispria/<version> (+project address)`), no bulk or offline use of
tiles, and for Nominatim: **at most one request a second for the whole application, answers cached, no
search-as-you-type**. Avispria searches only when you press the button, waits 1.1 seconds between searches,
and remembers answers for an hour. Because Avispria is shared by many people, the service addresses can be
changed ("Map background and place search settings") to another Nominatim-compatible service, for example
your own or a commercial one, and to another tile source, without a new version of the program.

## Not verified

The drawing and the browser's location have only been tried on one computer by the founder; the search was
tested against a stand-in for the service (Nominatim's documented answer format), not the live service from
the development environment.
