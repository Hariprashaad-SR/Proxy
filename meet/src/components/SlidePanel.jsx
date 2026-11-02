export default function SlidePanel({ slide }) {
  return (
    <div className="slide-card">
      <div className="slide-card-header">
        <span>{slide.title}</span>
        <span className="muted small">
          Slide {slide.index + 1} / {slide.total}
        </span>
      </div>
      {slide.imageUrl ? (
        <div className="slide-card-image">
          <img src={slide.imageUrl} alt={`${slide.title} — slide ${slide.index + 1}`} />
        </div>
      ) : (
        <div className="slide-card-body">{slide.text}</div>
      )}
    </div>
  );
}
