/**
 * Real routes for the sidebar sections that aren't built yet. Having them
 * routable now means navigation works end-to-end and each page has somewhere
 * to grow into, rather than dead links.
 */
export default function Placeholder({ title, blurb, planned = [] }) {
  return (
    <div className="placeholder-page">
      <h2>{title}</h2>
      <p className="placeholder-blurb">{blurb}</p>
      {planned.length > 0 && (
        <>
          <h4 className="placeholder-sub">Planned for this page</h4>
          <ul className="placeholder-list">
            {planned.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
