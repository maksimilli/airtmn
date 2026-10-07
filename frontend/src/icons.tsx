export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, string> = {
    grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
    search: "M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
    plus: "M12 5v14 M5 12h14",
    upload: "M12 16V3 M7 8l5-5 5 5 M4 15v6h16v-6",
    document: "M14 2H5v20h14V7z M14 2v5h5 M8 12h8 M8 16h8",
    arrow: "M5 12h14 M14 7l5 5-5 5",
    back: "M19 12H5 M10 7l-5 5 5 5",
    check: "M5 12l4 4L19 6",
    download: "M12 3v12 M7 10l5 5 5-5 M4 17v4h16v-4",
    help: "M9 9a3 3 0 0 1 6 0c0 3-3 2-3 5 M12 18h.01 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
    compare: "M4 3v18 M20 3v18 M4 8h6v8H4 M14 6h6v8h-6",
    edit: "M16 3l5 5-12 12-6 1 1-6z M13 6l5 5",
    trash: "M3 6h18 M9 6V3h6v3 M5 6l1 15h12l1-15",
    diode: "M2 12h5 M17 12h5 M7 6v12l10-6z M17 6v12",
    transistor: "M4 12h5 M9 4v16 M9 8l9-5 M9 16l9 5 M14 18l4 3-1-5",
    chip: "M6 6h12v12H6z M9 2v4 M15 2v4 M9 18v4 M15 18v4 M2 9h4 M2 15h4 M18 9h4 M18 15h4",
    resistor: "M1 12h4l2-5 3 10 4-10 3 10 2-5h4",
    capacitor: "M2 12h7 M9 5v14 M15 5v14 M15 12h7",
    inductor: "M2 12h2c0-8 4-8 4 0 0-8 4-8 4 0 0-8 4-8 4 0 0-8 4-8 4 0h2",
    connector: "M7 2v5 M17 2v5 M5 7h14v6l-7 5-7-5z M12 18v4",
    power: "M13 2 4 14h7l-1 8 10-13h-7z",
    box: "M3 7l9-5 9 5v10l-9 5-9-5z M3 7l9 5 9-5 M12 12v10",
    folder: "M3 5h7l2 3h9v12H3z",
    warning: "M12 3 2 21h20z M12 9v5 M12 17h.01",
    menu: "M3 6h18 M3 12h18 M3 18h18",
    settings: "M4 7h16 M4 17h16 M8 4v6 M16 14v6",
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] || paths.box} />
    </svg>
  );
}
