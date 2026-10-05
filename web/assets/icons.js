// أيقونات خطية بسيطة (SVG داخلي، دون ملفات خارجية). زخرفية دائمًا: aria-hidden، والمعنى في النص المجاور.
const P = {
  chart: '<path d="M4 20V11M10 20V5M16 20v-7M3 20h18"/>',
  code: '<path d="M8 8l-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14"/>',
  palette: '<path d="M12 3a9 9 0 1 0 0 18c1.1 0 1.6-.8 1.4-1.7-.3-1 .4-2 1.5-2H17a4 4 0 0 0 4-4C21 7.6 17 3 12 3z"/><circle cx="7.5" cy="11.5" r="1.1" fill="currentColor"/><circle cx="10" cy="7.3" r="1.1" fill="currentColor"/><circle cx="14.6" cy="7.6" r="1.1" fill="currentColor"/>',
  shield: '<path d="M12 3l7 3v6c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/>',
  server: '<rect x="4" y="4" width="16" height="6" rx="1.6"/><rect x="4" y="14" width="16" height="6" rx="1.6"/><path d="M8 7h.01M8 17h.01"/>',
  antenna: '<path d="M12 11v10M8.5 21h7"/><circle cx="12" cy="9.5" r="1.6"/><path d="M8.6 6.4a5 5 0 0 0 0 6.2M15.4 6.4a5 5 0 0 1 0 6.2M5.8 3.8a9 9 0 0 0 0 11.4M18.2 3.8a9 9 0 0 1 0 11.4"/>',
  chip: '<rect x="7" y="7" width="10" height="10" rx="1.5"/><path d="M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4"/>',
  check: '<circle cx="12" cy="12" r="9"/><path d="M8 12.2l2.8 2.8L16 9.5"/>',
  calendar: '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M8.5 3v4M15.5 3v4M8 14h3"/>',
  gear: '<circle cx="12" cy="12" r="3.2"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>',
  flow: '<circle cx="5.5" cy="6" r="2.3"/><circle cx="18.5" cy="6" r="2.3"/><circle cx="12" cy="18" r="2.3"/><path d="M7.8 6h8.4M6.8 8l4 7.8M17.2 8l-4 7.8"/>',
  megaphone: '<path d="M3.5 10v4h3l7 4.5v-13l-7 4.5z"/><path d="M17 9.2a4 4 0 0 1 0 5.6M19.4 6.8a7.5 7.5 0 0 1 0 10.4"/>',
  chat: '<path d="M4 5h16v11H9.5L5 20v-4H4z"/><path d="M8 9.5h8M8 12.5h5"/>',
  handshake: '<circle cx="8.5" cy="7.5" r="3.2"/><path d="M2.5 20a6 6 0 0 1 12 0"/><circle cx="16.5" cy="8.5" r="2.6"/><path d="M15.5 13.6A5 5 0 0 1 21.5 18.5"/>',
  compass: '<circle cx="12" cy="12" r="9"/><path d="M14.8 9.2l-1.6 4-4 1.6 1.6-4z"/>',
  scale: '<path d="M12 4v16M7.5 20h9M5 7.5h14"/><path d="M5 7.5l-2.6 5.5a2.6 2.6 0 0 0 5.2 0zM19 7.5l-2.6 5.5a2.6 2.6 0 0 0 5.2 0z"/>',
  bulb: '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.7.5 1.1 1.3 1.1 2.1V16h5v-.1c0-.8.4-1.6 1.1-2.1A6 6 0 0 0 12 3z"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M20 20l-4.7-4.7"/>',
  flask: '<path d="M9 3h6M10 3v6.2L4.8 18.5A1.8 1.8 0 0 0 6.4 21h11.2a1.8 1.8 0 0 0 1.6-2.5L14 9.2V3"/><path d="M7.5 15h9"/>',
  flag: '<path d="M5 21V4M5 4.5h11.5l-2.2 4 2.2 4H5"/>',
  pause: '<path d="M9 6v12M15 6v12"/>',
  play: '<path d="M8 5.5v13l10-6.5z"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.5-4.6L4 8M4 4v4h4M4 13a8 8 0 0 0 14.5 4.6L20 16M20 20v-4h-4"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>',
};

export function icon(name, size = 24, cls = "") {
  return `<svg class="ico ${cls}" viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true" focusable="false"
    fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${P[name] || P.compass}</svg>`;
}
