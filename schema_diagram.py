"""Render the actual local SQLite schema as an SVG and Mermaid ERD."""
from html import escape
from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parent


def main():
    with sqlite3.connect((ROOT/'data/fx-samples.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as db:
        tables={name:db.execute(f'PRAGMA table_info({name})').fetchall() for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")}
        definitions={name:sql for name,sql in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'")}
    order=[name for name in ['samples','stock_cost_basis','option_premiums','recommendation_runs'] if name in tables]
    width=max(1500,len(order)*500);height=820
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc"><title id="title">SQLite entity relationship diagram</title><desc id="desc">Four independent tables: FX samples, stock cost basis, opening option premiums and recommendation runs. No foreign keys are defined. Recommendation snapshots embed copies of source records as JSON.</desc><style>text{{font-family:Arial,sans-serif;fill:#193149}}.h{{font-size:22px;font-weight:bold}}.f{{font-family:monospace;font-size:15px}}.n{{font-size:16px;fill:#52697f}}</style><rect width="{width}" height="{height}" fill="#f3f6fa"/><text x="35" y="42" class="h">Investment SQLite · actual schema</text><text x="35" y="74" class="n">fx-samples.sqlite3 · PK = primary key · UK = unique key · nullable fields marked ?</text>']
    mermaid=['erDiagram']
    for i,name in enumerate(order):
        x=30+i*500;columns=tables[name];boxheight=90+len(columns)*26
        svg.append(f'<rect x="{x}" y="105" width="470" height="{boxheight}" rx="10" fill="white" stroke="#b4c7da"/><path d="M{x} 158H{x+470}" stroke="#b4c7da"/><text x="{x+18}" y="140" class="h">{name}</text>')
        mermaid.append(f'    {name} {{')
        for j,(_,field,kind,required,default,pk) in enumerate(columns):
            key='PK' if pk else 'UK' if field=='fingerprint' else ''
            nullable='' if required or pk else ' ?'
            line=f'{field}{nullable}  {kind}'+('  '+key if key else '')
            svg.append(f'<text x="{x+18}" y="{187+j*26}" class="f">{escape(line)}</text>')
            mermaid.append(f'        {kind.lower()} {field}'+(' '+key if key else ''))
        mermaid.append('    }')
        note='Unique: fingerprint' if name=='samples' else 'Composite unique key; see documentation' if name=='option_premiums' else 'Unique: account, symbol, currency' if name=='stock_cost_basis' else 'snapshot_json and usage_json are TEXT'
        svg.append(f'<text x="{x+18}" y="{105+boxheight-17}" class="n">{escape(note)}</text>')
    svg.append('<text x="35" y="700" class="h">Relationships</text><text x="35" y="733" class="n">No foreign keys are defined; the tables are intentionally shown without relationship lines.</text><text x="35" y="762" class="n">Recommendations copy source records and calculated results into snapshot_json; these are not enforced relational links.</text><text x="35" y="791" class="n">Stock basis is authoritative in stock_cost_basis; average cost = total_cost / quantity.</text></svg>')
    content=''.join(svg)
    (ROOT/'docs/database-erd.svg').write_text(content)
    (ROOT/'reports/database-erd.svg').write_text(content)
    md='''# Investment database ERD

Database: `coveredCallOptimizer/data/fx-samples.sqlite3`.
This diagram is generated from the actual schema. No foreign keys currently exist.

![Actual SQLite tables](database-erd.svg)

```mermaid
'''+ '\n'.join(mermaid)+'''
```

- `samples`: reviewed FX observations used to train the CIBC FX model.
  `fingerprint` is unique. `trade_date`, `commission_usd` and `yahoo_close` may be null.
- `stock_cost_basis`: shared stock basis, uniquely keyed by `(account, symbol, currency)`.
  Average cost is computed as `total_cost / quantity`. Optional purchase detail fields
  preserve date, USD price, fees and historical FX.
- `option_premiums`: opening call confirmations. The composite unique key is
  `(account, symbol, expiry, strike, contracts, settlement_date)`.
- `recommendation_runs`: saved OpenAI assessments and immutable input snapshots.
  `snapshot_json` contains copies of source data, the scenario and calculations;
  it is not a foreign-key reference. `usage_json` contains API token usage.
  `response_id` may be null.

The shared account/ticker/date values do not enforce relationships between tables.
An opening-premium confirmation may also have an FX observation in `samples`;
these are separate records with no linking foreign key. Stock basis and quantity are authoritative in `stock_cost_basis`; browser-only
legacy values can be explicitly imported through Profile settings.

Regenerate: `python3 coveredCallOptimizer/schema_diagram.py`. This reads the database
without modifying it and writes the documentation and browser SVG copies.
'''
    (ROOT/'docs/database-erd.md').write_text(md)
    print(ROOT/'docs/database-erd.svg')


if __name__=='__main__':main()
