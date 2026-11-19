// FloorPlanSVG.jsx - draws one floor as SVG from the plan JSON (rooms, doors, windows, parking).
// No image AI is involved: every line comes from coordinates in feet.
const SCALE = 14;   // pixels per foot
const MARGIN = 38;  // space around the plot for dimension text
const ROAD_H = 26;  // road strip under the bottom edge
const LEGEND_H = 62;

const ft = (value) => MARGIN + value * SCALE;           // feet -> pixel position
const fmt = (n) => Number(n.toFixed(1));
const dims = (w, h) => `${fmt(w)}' x ${fmt(h)}'`;

// For each wall: where it starts, the direction along it, and the inward direction (into the room).
const WALLS = {
  N: (r) => ({ x: r.x, y: r.y, dx: 1, dy: 0, nx: 0, ny: 1 }),
  S: (r) => ({ x: r.x, y: r.y + r.height, dx: 1, dy: 0, nx: 0, ny: -1 }),
  W: (r) => ({ x: r.x, y: r.y, dx: 0, dy: 1, nx: 1, ny: 0 }),
  E: (r) => ({ x: r.x + r.width, y: r.y, dx: 0, dy: 1, nx: -1, ny: 0 }),
};

// Pixel start (a), end (b) and inward direction of a door or window on its wall.
function openingGeometry(room, opening) {
  const w = WALLS[opening.wall](room);
  const a = { x: ft(w.x + w.dx * opening.offset), y: ft(w.y + w.dy * opening.offset) };
  const len = opening.width * SCALE;
  const b = { x: a.x + w.dx * len, y: a.y + w.dy * len };
  return { a, b, len, n: { x: w.nx, y: w.ny } };
}

// Names that do not fit on one line are split in half at a space.
function nameLines(name, widthPx, fontSize) {
  if (name.length * fontSize * 0.58 <= widthPx - 6 || !name.includes(" ")) return [name];
  const words = name.split(" ");
  const half = Math.ceil(words.length / 2);
  return [words.slice(0, half).join(" "), words.slice(half).join(" ")];
}

function RoomLabel({ room }) {
  const widthPx = room.width * SCALE;
  const size = widthPx < 80 ? 9 : 11;
  const lines = [...nameLines(room.name, widthPx, size), dims(room.width, room.height)];
  const lineHeight = size + 2;
  const cx = ft(room.x + room.width / 2);
  const cy = ft(room.y + room.height / 2) - ((lines.length - 1) * lineHeight) / 2 + size / 3;
  return (
    <text className="room-label" fontSize={size} textAnchor="middle">
      {lines.map((line, i) => (
        <tspan key={i} x={cx} y={cy + i * lineHeight} className={i === lines.length - 1 ? "room-dims" : ""}>
          {line}
        </tspan>
      ))}
    </text>
  );
}

// Stair treads: parallel lines across the shorter side of a staircase room.
function StairLines({ room }) {
  const lines = [];
  const alongY = room.height >= room.width;
  const count = Math.floor((alongY ? room.height : room.width) / 0.9);
  for (let i = 1; i < count; i++) {
    const step = (i * (alongY ? room.height : room.width)) / count;
    lines.push(alongY
      ? <line key={i} x1={ft(room.x)} x2={ft(room.x + room.width)} y1={ft(room.y + step)} y2={ft(room.y + step)} />
      : <line key={i} y1={ft(room.y)} y2={ft(room.y + room.height)} x1={ft(room.x + step)} x2={ft(room.x + step)} />);
  }
  return <g className="stair-lines">{lines}</g>;
}

// Erases the wall where a door or window sits, so the opening shows as a gap.
function WallGap({ room, opening }) {
  const { a, b } = openingGeometry(room, opening);
  return <line className="wall-gap" x1={a.x} y1={a.y} x2={b.x} y2={b.y} />;
}

// Door = leaf line + quarter-circle swing arc, opening into the room.
function Door({ room, door }) {
  const { a, b, len, n } = openingGeometry(room, door);
  const leaf = { x: a.x + n.x * len, y: a.y + n.y * len };
  const cross = (b.x - a.x) * (leaf.y - a.y) - (b.y - a.y) * (leaf.x - a.x);
  const sweep = cross > 0 ? 1 : 0; // picks the arc direction that curves toward the open leaf
  return (
    <g className={door.kind === "main" ? "door door-main" : "door"}>
      <line x1={a.x} y1={a.y} x2={leaf.x} y2={leaf.y} />
      <path d={`M ${b.x} ${b.y} A ${len} ${len} 0 0 ${sweep} ${leaf.x} ${leaf.y}`} />
    </g>
  );
}

// Window = two thin parallel lines in the wall gap.
function Window({ room, win }) {
  const { a, b, n } = openingGeometry(room, win);
  const off = 1.6;
  return (
    <g className="window">
      <line x1={a.x + n.x * off} y1={a.y + n.y * off} x2={b.x + n.x * off} y2={b.y + n.y * off} />
      <line x1={a.x - n.x * off} y1={a.y - n.y * off} x2={b.x - n.x * off} y2={b.y - n.y * off} />
    </g>
  );
}

const PARKING_NAMES = { two_wheeler: "Two-Wheeler Parking", "1_car": "Car Parking", "2_cars": "Car Parking (2 cars)" };

function ParkingArea({ parking }) {
  const label = `${PARKING_NAMES[parking.type]} ${dims(parking.width, parking.height)}`;
  return (
    <g>
      <rect className="parking" x={ft(parking.x)} y={ft(parking.y)} width={parking.width * SCALE} height={parking.height * SCALE} />
      <text className="room-label" fontSize="10" textAnchor="middle"
            x={ft(parking.x + parking.width / 2)} y={ft(parking.y + parking.height / 2)}>
        <tspan x={ft(parking.x + parking.width / 2)}>{PARKING_NAMES[parking.type]}</tspan>
        <tspan x={ft(parking.x + parking.width / 2)} dy="13" className="room-dims">{dims(parking.width, parking.height)}</tspan>
      </text>
      <title>{label}</title>
    </g>
  );
}

// `parking` should only be passed for the ground floor.
export default function FloorPlanSVG({ floor, parking, plotWidth, plotLength }) {
  const roomByName = Object.fromEntries(floor.rooms.map((r) => [r.name, r]));
  const withRoom = (items) => items.filter((o) => roomByName[o.room]);
  const plotW = plotWidth * SCALE;
  const plotH = plotLength * SCALE;
  const width = plotW + MARGIN * 2;
  const height = plotH + MARGIN + ROAD_H + LEGEND_H;
  const legendY = MARGIN + plotH + ROAD_H + 22;

  return (
    <svg className="floorplan" viewBox={`0 0 ${width} ${height}`} role="img"
         aria-label={`${floor.name} plan of a ${plotWidth} by ${plotLength} foot plot`}>
      <rect className="paper" width={width} height={height} />

      <rect className="road" x={MARGIN} y={MARGIN + plotH} width={plotW} height={ROAD_H} />
      <text className="road-label" x={MARGIN + plotW / 2} y={MARGIN + plotH + 17} textAnchor="middle">ROAD / GATE SIDE</text>

      {floor.rooms.map((r) => (
        <g key={r.name}>
          <rect className={`room room-${r.type}`} x={ft(r.x)} y={ft(r.y)} width={r.width * SCALE} height={r.height * SCALE} />
          {r.type === "staircase" && <StairLines room={r} />}
        </g>
      ))}
      {parking && <ParkingArea parking={parking} />}

      <rect className="plot-outline" x={MARGIN} y={MARGIN} width={plotW} height={plotH} />

      {[...withRoom(floor.doors), ...withRoom(floor.windows)].map((o, i) => (
        <WallGap key={`g${i}`} room={roomByName[o.room]} opening={o} />
      ))}
      {withRoom(floor.windows).map((w, i) => <Window key={`w${i}`} room={roomByName[w.room]} win={w} />)}
      {withRoom(floor.doors).map((d, i) => <Door key={`d${i}`} room={roomByName[d.room]} door={d} />)}
      {floor.rooms.map((r) => <RoomLabel key={r.name} room={r} />)}

      <text className="dim-text" x={MARGIN + plotW / 2} y={MARGIN - 14} textAnchor="middle">{fmt(plotWidth)}' (plot width)</text>
      <text className="dim-text" transform={`translate(${MARGIN - 14} ${MARGIN + plotH / 2}) rotate(-90)`} textAnchor="middle">
        {fmt(plotLength)}' (plot length)
      </text>

      <g className="scale-bar">
        <line x1={MARGIN} y1={legendY} x2={MARGIN + 10 * SCALE} y2={legendY} />
        <line x1={MARGIN} y1={legendY - 4} x2={MARGIN} y2={legendY + 4} />
        <line x1={MARGIN + 10 * SCALE} y1={legendY - 4} x2={MARGIN + 10 * SCALE} y2={legendY + 4} />
        <text x={MARGIN + 5 * SCALE} y={legendY - 7} textAnchor="middle">10 ft</text>
        <text x={MARGIN} y={legendY + 22}>Scale: 1 ft = {SCALE}px. Concept drawing, not for construction.</text>
      </g>
    </svg>
  );
}
