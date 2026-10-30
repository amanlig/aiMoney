import {html, useLayoutEffect, useRef} from './ui.js';

export function Input(props) {
  return props.type === 'date' ? html`<${DateInput} ...${props}/>` : html`<input ...${props}/>`;
}

const segments = [[0, 4], [5, 7], [8, 10]];
const validDate = value => /^\d{4}-\d{2}-\d{2}$/.test(value) && !value.startsWith('0000')
  && Number.isFinite(Date.parse(`${value}T00:00:00Z`))
  && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;

// Explicit ISO segments avoid browser/OS-dependent native date tab order.
// Keep draft text outside parent state until a complete, valid date is entered.
function DateInput({value = '', onChange, min, max, step, type, ...props}) {
  const node = useRef(), calendar = useRef();
  const reported = useRef(value), initial = useRef(value);
  const typing = useRef({segment: -1, digits: ''});
  const validate = () => {
    const text = node.current.value;
    node.current.setCustomValidity(text && !validDate(text) ? 'Enter a valid date as YYYY-MM-DD.'
      : validDate(text) && ((min && text < min) || (max && text > max)) ? 'Enter a date within the allowed range.' : '');
  };
  const publish = () => {
    validate();
    const text = node.current.value;
    const next = validDate(text) ? text : '';
    reported.current = next;
    if (calendar.current) calendar.current.value = next;
    onChange?.({target: {value: next}});
  };
  useLayoutEffect(() => {
    if (!node.current.hasAttribute('aria-label')) {
      const label = node.current.closest('label');
      if (label) node.current.setAttribute('aria-label', [...label.childNodes].filter(n => n.nodeType === Node.TEXT_NODE).map(n => n.textContent).join('').trim());
    }
    if (value !== reported.current) {
      node.current.value = value;
      calendar.current.value = value;
      reported.current = value;
      typing.current = {segment: -1, digits: ''};
    }
    validate();
  }, [value, min, max]);
  const select = index => {
    typing.current = {segment: -1, digits: ''};
    node.current.setSelectionRange(...segments[index]);
  };
  function keydown(event) {
    const field = node.current;
    const index = field.selectionStart < 5 ? 0 : field.selectionStart < 8 ? 1 : 2;
    if (event.key === 'Tab' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      const next = index + (event.shiftKey ? -1 : 1);
      if (next >= 0 && next < segments.length) {event.preventDefault(); select(next);}
      return;
    }
    if (event.ctrlKey || event.altKey || event.metaKey || !/^\d$/.test(event.key)) return;
    event.preventDefault();
    const [start, end] = segments[index];
    let draft = /^.{4}-.{2}-.{2}$/.test(field.value) ? field.value : '____-__-__';
    const prior = typing.current;
    const digits = prior.segment === index && prior.digits.length < end - start ? prior.digits + event.key : event.key;
    typing.current = {segment: index, digits};
    draft = draft.slice(0, start) + digits.padStart(end - start, '0') + draft.slice(end);
    field.value = draft;
    field.setSelectionRange(start, end);
    publish();
  }
  return html`<span className="date-entry">
    <input ...${props} ref=${node} type="text" inputMode="numeric" placeholder="YYYY-MM-DD"
      maxLength="10" defaultValue=${initial.current} onKeyDown=${keydown}
      onClick=${() => {typing.current = {segment: -1, digits: ''};}}
      onChange=${() => {typing.current = {segment: -1, digits: ''}; publish();}}/>
    <input ref=${calendar} type="date" className="date-calendar" tabIndex="-1" aria-hidden="true"
      disabled=${props.disabled} min=${min} max=${max} defaultValue=${initial.current}
      onChange=${event => {node.current.value = event.target.value; publish(); node.current.focus();}}/>
    <button type="button" className="date-picker-button" aria-label="Open calendar"
      disabled=${props.disabled} onClick=${() => calendar.current.showPicker()}>▦</button>
  </span>`;
}
