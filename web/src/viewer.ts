/** Fit is based only on width. Keyboard height changes never reduce desktop scale. */
export class DesktopViewer {
  private ratio = 16 / 9;
  private zoom = 1;
  private x = 0;
  private y = 0;
  private contacts = new Map<number, { x: number; y: number }>();
  private observer: ResizeObserver;
  private enabled = true;
  private orientation: "portrait" | "landscape" = "portrait";
  private states = {
    portrait: { zoom: 1, x: 0, y: 0 },
    landscape: { zoom: 1, x: 0, y: 0 },
  };
  private pinch?: {
    distance: number;
    zoom: number;
    x: number;
    y: number;
    center: { x: number; y: number };
  };

  constructor(
    private screen: HTMLElement,
    private picture: HTMLElement,
  ) {
    this.observer = new ResizeObserver(() => this.layout());
    this.observer.observe(screen);
    screen.addEventListener("pointerdown", (event) => {
      if (!this.enabled || (event.target as Element).closest("button")) return;
      event.preventDefault();
      screen.setPointerCapture(event.pointerId);
      this.contacts.set(event.pointerId, {
        x: event.clientX,
        y: event.clientY,
      });
      this.beginPinch();
    });
    screen.addEventListener("pointermove", (event) => {
      if (!this.enabled) return;
      const old = this.contacts.get(event.pointerId);
      if (!old) return;
      const dx = event.clientX - old.x,
        dy = event.clientY - old.y;
      this.contacts.set(event.pointerId, {
        x: event.clientX,
        y: event.clientY,
      });
      if (this.contacts.size === 2 && this.pinch && this.pinch.distance > 0) {
        const start = this.pinch;
        const nextZoom = Math.max(
          1,
          Math.min(5, (start.zoom * this.distance()) / start.distance),
        );
        const newCenter = this.centroid();
        const bounds = screen.getBoundingClientRect();
        const centerX = bounds.left + bounds.width / 2;
        const centerY = bounds.top + bounds.height / 2;
        // Preserve the image point under the fingers, including two-finger panning.
        // Coordinates are relative to the viewer center, matching the CSS transform.
        const imageX = (start.center.x - centerX - start.x) / start.zoom;
        const imageY = (start.center.y - centerY - start.y) / start.zoom;
        this.x = newCenter.x - centerX - imageX * nextZoom;
        this.y = newCenter.y - centerY - imageY * nextZoom;
        this.zoom = nextZoom;
      } else if (this.contacts.size === 1) {
        // At fit width a short viewport can still crop the image vertically.
        this.x += dx;
        this.y += dy;
      }
      this.layout();
      this.remember();
    });
    for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) {
      screen.addEventListener(name, (event) => {
        this.contacts.delete((event as PointerEvent).pointerId);
        this.beginPinch();
      });
    }
  }

  setAspect(width: number, height: number) {
    this.ratio = width / height;
    this.layout();
  }

  reset() {
    this.zoom = 1;
    this.x = this.y = 0;
    this.layout();
    this.remember();
  }

  setEnabled(enabled: boolean) {
    this.enabled = enabled;
    this.contacts.clear();
    this.pinch = undefined;
  }

  setOrientation(orientation: "portrait" | "landscape") {
    if (orientation === this.orientation) return;
    this.orientation = orientation;
    const state = this.states[orientation];
    this.zoom = state.zoom;
    this.x = state.x;
    this.y = state.y;
    this.contacts.clear();
    this.pinch = undefined;
    this.layout();
  }

  private remember() {
    this.states[this.orientation] = { zoom: this.zoom, x: this.x, y: this.y };
  }

  private beginPinch() {
    this.pinch =
      this.contacts.size === 2
        ? {
            distance: this.distance(),
            zoom: this.zoom,
            x: this.x,
            y: this.y,
            center: this.centroid(),
          }
        : undefined;
  }

  private centroid() {
    const points = [...this.contacts.values()];
    return {
      x: points.reduce((sum, point) => sum + point.x, 0) / points.length,
      y: points.reduce((sum, point) => sum + point.y, 0) / points.length,
    };
  }

  private distance() {
    const points = [...this.contacts.values()];
    return points.length === 2
      ? Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y)
      : 0;
  }

  private layout() {
    const width =
        this.orientation === "landscape"
          ? Math.min(
              this.screen.clientWidth,
              this.screen.clientHeight * this.ratio,
            )
          : this.screen.clientWidth,
      height = width / this.ratio;
    const limitX = Math.max(
      0,
      (width * this.zoom - this.screen.clientWidth) / 2,
    );
    const limitY = Math.max(
      0,
      (height * this.zoom - this.screen.clientHeight) / 2,
    );
    this.x = Math.max(-limitX, Math.min(limitX, this.x));
    this.y = Math.max(-limitY, Math.min(limitY, this.y));
    this.picture.style.width = `${width}px`;
    this.picture.style.height = `${height}px`;
    this.picture.style.transform = `translate(-50%, -50%) translate(${this.x}px, ${this.y}px) scale(${this.zoom})`;
  }
}
