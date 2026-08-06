import type { ReactNode } from "react";

/** Rendu inline : **gras**, *italique*, `code`, et balises <br> */
function renderInline(text: string): ReactNode[] {
  const cleaned = text
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");

  const parts: ReactNode[] = [];
  const chunks = cleaned.split("\n");
  chunks.forEach((chunk, ci) => {
    if (ci > 0) parts.push(<br key={`br-${ci}`} />);
    const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
    let last = 0;
    let match: RegExpExecArray | null;
    let key = 0;
    while ((match = re.exec(chunk)) !== null) {
      if (match.index > last) parts.push(chunk.slice(last, match.index));
      const token = match[0];
      if (token.startsWith("**")) {
        parts.push(
          <strong key={`${ci}-b-${key++}`} className="font-semibold">
            {token.slice(2, -2)}
          </strong>
        );
      } else if (token.startsWith("*")) {
        parts.push(
          <em key={`${ci}-i-${key++}`} className="italic text-ink-soft">
            {token.slice(1, -1)}
          </em>
        );
      } else {
        parts.push(
          <code
            key={`${ci}-c-${key++}`}
            className="rounded bg-mist px-1 py-0.5 font-mono text-[0.8em]"
          >
            {token.slice(1, -1)}
          </code>
        );
      }
      last = match.index + token.length;
    }
    if (last < chunk.length) parts.push(chunk.slice(last));
  });
  return parts;
}

const DAY_ORDER = [
  "lundi",
  "mardi",
  "mercredi",
  "jeudi",
  "vendredi",
  "samedi",
  "dimanche",
];

type ScheduleItem = {
  dayKey: string;
  dayLabel: string;
  slot: string;
  course: string;
  details: string;
  sessionId?: string;
};

function slotSortKey(slot: string): number {
  const m = slot.match(/(\d{1,2})[h:](\d{2})/);
  if (!m) return 9999;
  return Number(m[1]) * 60 + Number(m[2]);
}

function daySortKey(dayKey: string): number {
  const i = DAY_ORDER.indexOf(dayKey);
  return i === -1 ? 99 : i;
}

function dayKeyFromLabel(label: string): string {
  const word = label.trim().split(/\s+/)[0]?.toLowerCase() || label.toLowerCase();
  return word.normalize("NFD").replace(/\p{M}/gu, "");
}

/** Format historique UI : `- **Lundi 03/08 (08:00 - 10:00)** : *Cours* … (Séance #1)` */
function parseBoldScheduleLine(line: string): ScheduleItem | null {
  const cleaned = line.replace(/^[-•*]\s+/, "").trim();
  const m = cleaned.match(
    /^\*\*(.+?)\*\*\s*:\s*\*(.+?)\*\s*(.*?)(?:\(Séance\s*#(\d+)\))?\s*$/i
  );
  if (!m) return null;
  const when = m[1].trim();
  const timeMatch = when.match(/\(([^)]+)\)/);
  const slot = timeMatch ? timeMatch[1].replace(/\s+/g, " ").trim() : "—";
  const dayPart = when.replace(/\([^)]*\)/, "").trim();
  return {
    dayKey: dayKeyFromLabel(dayPart),
    dayLabel: dayPart,
    slot,
    course: m[2],
    details: m[3].trim().replace(/\s*\(Séance.*$/i, "").trim(),
    sessionId: m[4],
  };
}

/**
 * Ligne type :
 * `- 08:00 - 10:00 : Bases de données (L3 Info A) avec Bruno Dupont en salle B202 — Séance #2`
 */
function parseTimeScheduleLine(
  line: string,
  dayLabel: string
): ScheduleItem | null {
  const cleaned = line.replace(/^[-•*]\s+/, "").trim();
  const m = cleaned.match(
    /^(\d{1,2}[:h]\d{2}\s*[-–—]\s*\d{1,2}[:h]\d{2})\s*:\s*(.+?)(?:[—\-–]\s*Séance\s*#(\d+)|\(Séance\s*#(\d+)\))?\s*$/i
  );
  if (!m) return null;
  const slot = m[1].replace(/[hH]/g, ":").replace(/\s+/g, " ").trim();
  const rest = m[2].trim();
  const sessionId = m[3] || m[4];
  // "Course (group) avec Teacher en salle X"
  const courseMatch = rest.match(/^([^(—]+?)(?:\s*\(|\s+avec\s+|$)/);
  const course = (courseMatch?.[1] || rest).trim();
  const details = rest
    .replace(course, "")
    .replace(/^\s*[:(]\s*/, "")
    .replace(/\)\s*/, ") ")
    .trim();
  return {
    dayKey: dayKeyFromLabel(dayLabel),
    dayLabel,
    slot,
    course,
    details,
    sessionId,
  };
}

function isDayHeader(line: string): string | null {
  const cleaned = line.replace(/^[-•*]\s+/, "").replace(/:$/, "").trim();
  const m = cleaned.match(
    /^(Lundi|Mardi|Mercredi|Jeudi|Vendredi|Samedi|Dimanche)\b(.*)$/i
  );
  if (!m) return null;
  return `${m[1]}${m[2] || ""}`.trim();
}

function parseMarkdownTable(lines: string[], start: number): {
  headers: string[];
  rows: string[][];
  nextIndex: number;
} | null {
  if (start >= lines.length || !lines[start].includes("|")) return null;
  const headerLine = lines[start].trim();
  if (!/\|/.test(headerLine)) return null;
  const sep = lines[start + 1]?.trim() || "";
  if (!/^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$/.test(sep)) return null;

  const splitRow = (row: string) =>
    row
      .replace(/^\|/, "")
      .replace(/\|$/, "")
      .split("|")
      .map((c) => c.trim());

  const headers = splitRow(headerLine);
  const rows: string[][] = [];
  let i = start + 2;
  while (i < lines.length && lines[i].includes("|")) {
    const t = lines[i].trim();
    if (!t || /^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$/.test(t)) {
      i++;
      continue;
    }
    rows.push(splitRow(t));
    i++;
  }
  return { headers, rows, nextIndex: i };
}

function htmlToText(cell: string): string {
  return cell
    .replace(/<br\s*\/?>/gi, " · ")
    .replace(/<[^>]+>/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** Convertit une table markdown planning → items pour la grille. */
function scheduleItemsFromTable(
  headers: string[],
  rows: string[][]
): ScheduleItem[] | null {
  const h = headers.map((x) => x.toLowerCase());

  // Format liste : Jour | Horaire | Cours | Enseignant | Groupe | Salle | N°
  const jourIdx = h.findIndex((x) => x.includes("jour"));
  const horaireIdx = h.findIndex(
    (x) => x.includes("horaire") || x.includes("créneau") || x.includes("creneau")
  );
  const coursIdx = h.findIndex((x) => x.includes("cours"));
  if (jourIdx >= 0 && horaireIdx >= 0 && coursIdx >= 0) {
    const items: ScheduleItem[] = [];
    for (const row of rows) {
      const dayLabel = htmlToText(row[jourIdx] || "");
      const slot = htmlToText(row[horaireIdx] || "");
      const course = htmlToText(row[coursIdx] || "");
      if (!dayLabel || !course || course === "—") continue;
      const teacher = htmlToText(row[h.findIndex((x) => x.includes("enseignant"))] || "");
      const group = htmlToText(row[h.findIndex((x) => x.includes("groupe"))] || "");
      const room = htmlToText(row[h.findIndex((x) => x.includes("salle"))] || "");
      const seance = htmlToText(
        row[h.findIndex((x) => x.includes("séance") || x.includes("seance") || x.includes("n°"))] ||
          ""
      );
      const sessionId = seance.match(/#?(\d+)/)?.[1];
      const details = [teacher && `avec ${teacher}`, group, room && `salle ${room}`]
        .filter(Boolean)
        .join(" · ");
      items.push({
        dayKey: dayKeyFromLabel(dayLabel),
        dayLabel,
        slot,
        course,
        details,
        sessionId,
      });
    }
    return items.length ? items : null;
  }

  // Format grille : Horaires/Jours | Lundi | Mardi | …
  const first = h[0] || "";
  const dayCols = headers
    .map((label, idx) => ({ label, idx }))
    .filter(
      ({ label, idx }) =>
        idx > 0 &&
        /lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche/i.test(label)
    );
  if (
    dayCols.length >= 2 &&
    (first.includes("horaire") || first.includes("jour") || first.includes("/"))
  ) {
    const items: ScheduleItem[] = [];
    for (const row of rows) {
      const slot = htmlToText(row[0] || "");
      if (!slot || /après-midi|apres-midi|—|^-$/i.test(slot)) continue;
      if (!/\d/.test(slot)) continue;
      for (const { label, idx } of dayCols) {
        const raw = row[idx] || "";
        const cell = raw.replace(/<br\s*\/?>/gi, "\n").trim();
        if (!cell || cell === "—" || cell === "-") continue;
        // Plusieurs séances séparées par lignes vides / doubles sauts
        const blocks = cell.split(/\n\s*\n/).map((b) => b.trim()).filter(Boolean);
        for (const block of blocks.length ? blocks : [cell]) {
          const lines = block
            .split("\n")
            .map((l) => l.replace(/<[^>]+>/g, "").trim())
            .filter(Boolean);
          const course = lines[0] || "Cours";
          if (course === "—") continue;
          const joined = lines.join(" ");
          const sessionId = joined.match(/Séance\s*#(\d+)/i)?.[1];
          const details = lines.slice(1).join(" · ").replace(/\(Séance\s*#\d+\)/gi, "").trim();
          items.push({
            dayKey: dayKeyFromLabel(label),
            dayLabel: label.replace(/\s*\(.*\)/, "").trim(),
            slot: slot.replace(/\s+/g, " "),
            course: course.replace(/\(.*\)/, "").trim() || course,
            details,
            sessionId,
          });
        }
      }
    }
    return items.length ? items : null;
  }

  return null;
}

function MarkdownTable({
  headers,
  rows,
}: {
  headers: string[];
  rows: string[][];
}) {
  return (
    <div className="my-3 overflow-x-auto rounded-xl border border-line">
      <table className="w-full min-w-[24rem] border-collapse text-left text-xs">
        <thead>
          <tr className="bg-mist/80">
            {headers.map((h, i) => (
              <th
                key={i}
                className="px-3 py-2.5 font-semibold text-ink-soft border-b border-line whitespace-nowrap"
              >
                {htmlToText(h)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri}>
              {headers.map((_, ci) => (
                <td
                  key={ci}
                  className="px-3 py-2 border-t border-line align-top leading-relaxed"
                >
                  {renderInline(row[ci] || "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ScheduleGrid({ items }: { items: ScheduleItem[] }) {
  const slots = [...new Set(items.map((it) => it.slot))].sort(
    (a, b) => slotSortKey(a) - slotSortKey(b)
  );

  const daysMap = new Map<
    string,
    { label: string; bySlot: Map<string, ScheduleItem[]> }
  >();
  for (const item of items) {
    if (!daysMap.has(item.dayKey)) {
      daysMap.set(item.dayKey, { label: item.dayLabel, bySlot: new Map() });
    }
    const day = daysMap.get(item.dayKey)!;
    const list = day.bySlot.get(item.slot) || [];
    list.push(item);
    day.bySlot.set(item.slot, list);
  }

  const days = [...daysMap.entries()].sort(
    (a, b) => daySortKey(a[0]) - daySortKey(b[0])
  );

  return (
    <div className="my-3 -mx-1 overflow-x-auto rounded-xl border border-line bg-paper/60">
      <table className="w-full min-w-[28rem] border-collapse text-left text-xs">
        <thead>
          <tr className="bg-mist/80">
            <th className="sticky left-0 z-10 bg-mist px-3 py-2.5 font-semibold text-ink-soft w-28 border-b border-line">
              Jour
            </th>
            {slots.map((slot) => (
              <th
                key={slot}
                className="px-2 py-2.5 font-semibold text-ink-soft text-center border-b border-l border-line whitespace-nowrap"
              >
                {slot}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {days.map(([dayKey, day]) => (
            <tr key={dayKey} className="align-top">
              <th className="sticky left-0 z-10 bg-white px-3 py-2.5 font-semibold text-ink border-t border-line text-left whitespace-nowrap">
                {day.label}
              </th>
              {slots.map((slot) => {
                const cellItems = day.bySlot.get(slot) || [];
                return (
                  <td
                    key={slot}
                    className="px-1.5 py-1.5 border-t border-l border-line min-w-[7.5rem] bg-white"
                  >
                    {cellItems.length === 0 ? (
                      <div className="h-full min-h-14 rounded-lg bg-mist/40" />
                    ) : (
                      <div className="space-y-1">
                        {cellItems.map((it, idx) => (
                          <div
                            key={`${it.sessionId || it.course}-${idx}`}
                            className="rounded-lg border border-accent/25 bg-accent-soft/70 px-2 py-1.5"
                          >
                            <div className="font-semibold text-ink leading-snug">
                              {it.course}
                            </div>
                            {it.details ? (
                              <div className="text-[10px] text-ink-soft mt-0.5 leading-snug">
                                {it.details}
                              </div>
                            ) : null}
                            {it.sessionId ? (
                              <div className="mt-1 text-[10px] font-medium text-accent">
                                Séance #{it.sessionId}
                              </div>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** `- Algorithmique … : 8h restantes (4h faites / 12h prévues)` */
function parseHoursLine(line: string): {
  title: string;
  remaining: string;
  done?: string;
  planned?: string;
} | null {
  const cleaned = line.replace(/^[-•*]\s+/, "").trim();
  const m = cleaned.match(
    /^(.+?)\s*:\s*(\d+(?:[.,]\d+)?\s*h(?:eures?)?)\s*restantes?(?:\s*\((.+?)\))?/i
  );
  if (!m) return null;
  const detail = m[3] || "";
  const done = detail.match(/(\d+(?:[.,]\d+)?\s*h)\s*fait/i)?.[1];
  const planned = detail.match(/(\d+(?:[.,]\d+)?\s*h)\s*prévu/i)?.[1];
  return { title: m[1].trim(), remaining: m[2].trim(), done, planned };
}

function HoursCards({
  items,
}: {
  items: { title: string; remaining: string; done?: string; planned?: string }[];
}) {
  return (
    <div className="my-3 space-y-2">
      {items.map((it, i) => {
        const rem = parseFloat(it.remaining.replace(",", ".")) || 0;
        const plan =
          parseFloat((it.planned || "").replace(",", ".")) ||
          (it.done
            ? rem + (parseFloat(it.done.replace(",", ".")) || 0)
            : rem || 1);
        const doneH = plan - rem;
        const pct = Math.min(100, Math.round((doneH / plan) * 100));
        return (
          <div
            key={i}
            className="rounded-xl border border-line bg-white px-3 py-2.5"
          >
            <div className="flex justify-between gap-3 text-sm">
              <span className="font-semibold text-ink">{it.title}</span>
              <span className="text-accent font-medium whitespace-nowrap">
                {it.remaining} restantes
              </span>
            </div>
            <div className="mt-2 h-1.5 rounded-full bg-mist overflow-hidden">
              <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
            </div>
            <div className="mt-1 text-[11px] text-ink-soft">
              {it.done || `${doneH}h`} faites / {it.planned || `${plan}h`} prévues
            </div>
          </div>
        );
      })}
    </div>
  );
}

function collectHierarchicalSchedule(
  lines: string[],
  start: number
): { items: ScheduleItem[]; nextIndex: number } | null {
  const firstDay = isDayHeader(lines[start] || "");
  if (!firstDay) return null;
  // Need at least one following time line to confirm
  const peek = lines[start + 1] || "";
  if (!parseTimeScheduleLine(peek, firstDay) && !isDayHeader(peek)) {
    // day header alone then empty then time?
    let j = start + 1;
    while (j < lines.length && !lines[j].trim()) j++;
    if (!parseTimeScheduleLine(lines[j] || "", firstDay)) return null;
  }

  const items: ScheduleItem[] = [];
  let i = start;
  let currentDay: string | null = null;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    const day = isDayHeader(line);
    if (day) {
      currentDay = day;
      i++;
      continue;
    }
    if (currentDay) {
      const item = parseTimeScheduleLine(line, currentDay);
      if (item) {
        items.push(item);
        i++;
        continue;
      }
    }
    break;
  }
  return items.length ? { items, nextIndex: i } : null;
}

export function ChatMessageContent({
  content,
  variant,
}: {
  content: string;
  variant: "user" | "assistant";
}) {
  if (variant === "user") {
    return <span className="whitespace-pre-wrap">{content}</span>;
  }

  const lines = content.split(/\n/);
  const blocks: ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Markdown table
    const table = parseMarkdownTable(lines, i);
    if (table) {
      const scheduleItems = scheduleItemsFromTable(table.headers, table.rows);
      if (scheduleItems) {
        blocks.push(<ScheduleGrid key={key++} items={scheduleItems} />);
      } else {
        blocks.push(
          <MarkdownTable
            key={key++}
            headers={table.headers}
            rows={table.rows}
          />
        );
      }
      i = table.nextIndex;
      continue;
    }

    // Hierarchical day → time slots
    const hier = collectHierarchicalSchedule(lines, i);
    if (hier) {
      blocks.push(<ScheduleGrid key={key++} items={hier.items} />);
      i = hier.nextIndex;
      continue;
    }

    // Classic bold schedule lines
    if (parseBoldScheduleLine(line)) {
      const items: ScheduleItem[] = [];
      while (i < lines.length) {
        const item = parseBoldScheduleLine(lines[i]);
        if (!item) break;
        items.push(item);
        i++;
      }
      blocks.push(<ScheduleGrid key={key++} items={items} />);
      continue;
    }

    // Hours remaining block
    if (parseHoursLine(line)) {
      const items: {
        title: string;
        remaining: string;
        done?: string;
        planned?: string;
      }[] = [];
      while (i < lines.length) {
        const h = parseHoursLine(lines[i]);
        if (!h) {
          if (!lines[i].trim()) {
            i++;
            continue;
          }
          break;
        }
        items.push(h);
        i++;
      }
      blocks.push(<HoursCards key={key++} items={items} />);
      continue;
    }

    if (!line.trim()) {
      blocks.push(<div key={key++} className="h-2" />);
      i++;
      continue;
    }

    if (/^#{1,3}\s/.test(line)) {
      blocks.push(
        <div key={key++} className="font-semibold text-base mt-1 mb-1">
          {renderInline(line.replace(/^#{1,3}\s+/, ""))}
        </div>
      );
      i++;
      continue;
    }

    // Numbered options
    if (/^\d+\.\s+/.test(line.trim())) {
      const opts: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        opts.push(lines[i].trim().replace(/^\d+\.\s+/, ""));
        i++;
      }
      blocks.push(
        <ol key={key++} className="my-2 space-y-1.5 list-none">
          {opts.map((opt, idx) => (
            <li
              key={idx}
              className="flex gap-2.5 rounded-xl border border-line bg-white px-3 py-2 text-sm"
            >
              <span className="shrink-0 h-6 w-6 rounded-lg bg-accent-soft text-accent font-semibold text-xs grid place-items-center">
                {idx + 1}
              </span>
              <span className="leading-relaxed pt-0.5">{renderInline(opt)}</span>
            </li>
          ))}
        </ol>
      );
      continue;
    }

    blocks.push(
      <p key={key++} className="leading-relaxed my-0.5">
        {renderInline(line)}
      </p>
    );
    i++;
  }

  return <div className="space-y-0.5">{blocks}</div>;
}
