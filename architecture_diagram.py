"""Render the proposed single-EC2 deployment as a self-contained SVG."""
import base64
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 1800, 1530


def render():
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title description">
<title id="title">Covered Call Optimizer — proposed AWS deployment</title>
<desc id="description">Proposed, not yet deployed to AWS. Route 53 maps a subdomain to an Elastic IP on one EC2 instance. The browser connects over HTTPS to a planned Caddy container. An existing application container serves React assets and FastAPI, application services and a pure financial model. A separate existing PostgreSQL container holds records. Both use persistent EBS storage. Questrade, Yahoo Finance and OpenAI are external services. Docker images are build inputs, not additional servers. S3 holds proposed off-instance backups. PostgreSQL and application ports are not publicly exposed.</desc>
<defs>
 <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8Z" fill="#536b82"/></marker>
 <marker id="dns" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8Z" fill="#8159a4"/></marker>
</defs>
<style>
text{{font-family:Arial,Helvetica,sans-serif;fill:#18324c}}
.title{{font-size:32px;font-weight:700}} .heading{{font-size:21px;font-weight:700}}
.body{{font-size:17px}} .small{{font-size:15px;fill:#50677d}} .tiny{{font-size:14px;fill:#50677d}}
.label{{font-size:15px;font-weight:700}} .light{{fill:white}}
</style>
<rect width="1800" height="1530" fill="#f4f7fb"/>
''']

    def text(x, y, value, css='body'):
        parts.append(f'<text x="{x}" y="{y}" class="{css}">{escape(value)}</text>')

    def rect(x, y, w, h, fill='white', stroke='#cdd8e4', dashed=False, radius=14):
        dash = ' stroke-dasharray="8 6"' if dashed else ''
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="2"{dash}/>')

    def icon(name, x, y, size=48):
        path = ROOT / 'docs/icons' / (name + '.png')
        if not path.exists():
            path = path.with_suffix('.svg')
        mime = 'image/svg+xml' if path.suffix == '.svg' else 'image/png'
        encoded = base64.b64encode(path.read_bytes()).decode()
        parts.append(f'<image x="{x}" y="{y}" width="{size}" height="{size}" href="data:{mime};base64,{encoded}"/>')

    def line(points, dashed=False, dns=False):
        color = '#8159a4' if dns else '#536b82'
        dash = ' stroke-dasharray="7 5"' if dashed else ''
        marker = 'dns' if dns else 'arrow'
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linejoin="round" marker-end="url(#{marker})"{dash}/>')

    def badge(x, y, value, color='#e9f2fd', ink='#24496d', width=150):
        rect(x, y, width, 28, color, color, radius=7)
        parts.append(f'<text x="{x+10}" y="{y+19}" style="font:700 13px Arial;fill:{ink}">{escape(value)}</text>')

    def brand(x, y, label, color, size=48):
        rect(x, y, size, size, color, color, radius=10)
        parts.append(f'<text x="{x+size/2}" y="{y+size*.66}" text-anchor="middle" style="font:700 {size*.4}px Arial;fill:white">{escape(label)}</text>')

    text(40, 53, 'Covered Call Optimizer · AWS deployment', 'title')
    text(40, 84, 'Planned manual deployment · one EC2 instance · three containers · October 23, 2026', 'body')
    badge(1405, 31, 'AWS NOT DEPLOYED', '#fff0d7', '#865412', 350)

    # DNS is a lookup; the browser's application traffic goes directly to EC2.
    rect(40, 135, 330, 135)
    parts.append('<rect x="62" y="157" width="52" height="38" rx="4" fill="#e4f0fc" stroke="#326da8" stroke-width="3"/><path d="M88 195v12m-15 0h30" stroke="#326da8" stroke-width="3"/>')
    text(130, 175, 'Trader’s browser', 'heading')
    text(62, 232, 'React runs here after download', 'small')
    rect(435, 135, 345, 135)
    icon('route53', 455, 155, 50)
    text(521, 175, 'Amazon Route 53', 'heading')
    text(455, 225, 'money.yourdomain.com', 'body')
    text(455, 249, 'A record → fixed Elastic IP', 'small')
    rect(845, 135, 330, 135, '#f2f7fd')
    brand(866, 157, 'IP', '#326da8')
    text(930, 175, 'Elastic IP', 'heading')
    text(866, 225, 'Stable public IPv4 address', 'body')
    text(866, 249, 'Retained across stop / start', 'small')
    line('370,185 435,185', True, True)
    text(378, 169, 'DNS', 'tiny')
    line('780,185 845,185', True, True)
    text(792, 169, 'maps', 'tiny')
    text(1240, 174, 'One public endpoint', 'heading')
    text(1240, 207, 'UI and API share the same HTTPS origin.', 'body')
    text(1240, 237, 'Login required before public access.', 'small')

    # AWS resources vs. third-party providers.
    rect(400, 335, 995, 1050, '#fffaf2', '#d9a14a', radius=20)
    text(425, 369, 'AWS · EC2 COMPUTE + STORAGE', 'label')
    rect(425, 395, 945, 725, '#ffffff', '#e79b43', radius=18)
    icon('ec2', 445, 415, 53)
    text(515, 438, 'Amazon EC2 · one Linux instance', 'heading')
    text(515, 465, 'Start when needed · Docker Compose restarts containers on boot', 'small')
    badge(1115, 420, '2 vCPU / 4 GB', '#fff0d7', '#865412', 230)
    rect(450, 493, 895, 600, '#f1f7fc', '#69a0cb', radius=15)
    icon('docker', 466, 503, 43)
    text(520, 530, 'Docker Compose · private container network', 'heading')

    rect(475, 555, 845, 105, '#fffdf8', '#c99843', dashed=True)
    icon('caddy', 493, 572, 55)
    text(568, 585, 'Caddy · HTTPS reverse proxy', 'heading')
    text(568, 614, 'TLS certificate + renewal · HTTP redirects to HTTPS', 'body')
    text(568, 639, 'Image: caddy:2     Container / service: caddy     Public ports: 80, 443', 'small')
    badge(1153, 570, 'TO ADD', '#fff0d7', '#865412', 143)

    line('205,270 205,305 1382,305 1382,543 900,543 900,555')
    rect(542, 290, 330, 30, '#f4f7fb', '#f4f7fb', radius=0)
    text(555, 311, 'HTTPS :443 → Elastic IP → EC2', 'label')
    text(921, 351, 'Security group: allow 80 / 443', 'small')
    line('735,660 735,723')
    text(752, 690, 'HTTP → api:8765', 'small')

    rect(475, 725, 535, 340, '#ffffff', '#4c91bd')
    icon('docker', 491, 737, 40)
    text(547, 758, 'Application container', 'heading')
    text(494, 789, 'Image: aimoney:<version> · service: api', 'small')
    icon('react', 493, 806, 36)
    text(544, 832, 'React assets · home, chart, settings', 'body')
    icon('fastapi', 493, 852, 36)
    text(544, 879, 'FastAPI · /api/* and static UI files', 'body')
    text(494, 920, 'Application services', 'label')
    text(494, 945, 'Broker access · records · captures · assessments', 'small')
    rect(494, 967, 495, 75, '#eaf7f2', '#b4d9ca', radius=9)
    text(510, 994, 'Independent financial model · Python', 'label')
    text(510, 1019, 'Pricing / simulation · no network or database access', 'small')

    rect(1050, 725, 270, 340, '#ffffff', '#487da8')
    icon('postgresql', 1139, 749, 80)
    text(1070, 870, 'PostgreSQL 17', 'heading')
    text(1070, 900, 'Image: postgres:17.6-', 'small')
    text(1070, 922, 'bookworm · service: db', 'small')
    text(1070, 958, 'Basis · premiums · FX', 'body')
    text(1070, 985, 'Recommendation history', 'small')
    badge(1070, 1010, 'PRIVATE :5432', '#e9f2fd', '#24496d', 230)
    line('1010,910 1050,910')

    # Image artifacts are not running services.
    rect(40, 395, 315, 725, '#ffffff', '#c7d4e1')
    icon('docker', 60, 414, 48)
    text(121, 443, 'Docker images', 'heading')
    text(60, 483, 'Build / pull, then run', 'body')
    text(60, 512, 'Artifacts, not extra EC2 instances', 'tiny')
    rect(60, 549, 275, 142, '#f2f7fd')
    text(77, 579, '1  Application image', 'label')
    text(77, 610, 'Built from our Dockerfile', 'small')
    text(77, 637, 'React + Python + model', 'small')
    text(77, 665, 'aimoney:<version>', 'small')
    rect(60, 713, 275, 142, '#f2f7fd')
    text(77, 744, '2  PostgreSQL image', 'label')
    text(77, 775, 'Official Docker Hub image', 'small')
    text(77, 802, 'Database engine only', 'small')
    text(77, 830, 'postgres:17.6-bookworm', 'small')
    rect(60, 877, 275, 142, '#fffdf8', '#c99843', dashed=True)
    text(77, 908, '3  Caddy image', 'label')
    text(77, 939, 'Official Docker Hub image', 'small')
    text(77, 966, 'HTTPS entry point · planned', 'small')
    text(77, 994, 'caddy:2', 'small')
    text(60, 1064, 'Manual build / transfer / pull', 'small')
    line('355,520 450,520', True)

    rect(1430, 395, 330, 725, '#ffffff', '#c7d4e1')
    text(1450, 432, 'EXTERNAL SERVICES', 'label')
    for y, label, mark, color, rows in [
        (465, 'Questrade API', 'Q', '#337a35', ('Quotes · Greeks · option chains', 'Positions · explicit refresh')),
        (667, 'Yahoo Finance', 'Y!', '#6001d2', ('Stock-price history', 'USD/CAD reference feed')),
        (869, 'OpenAI API', 'AI', '#157b68', ('Selected scenario snapshot', 'Assessment · explicit request')),
    ]:
        rect(1450, y, 290, 168, '#f8fafc')
        brand(1466, y+16, mark, color, 43)
        text(1521, y+44, label, 'heading')
        text(1466, y+92, rows[0], 'small')
        text(1466, y+120, rows[1], 'small')
    # All providers connect to app services, never directly to the pure model.
    line('970,725 970,694 1410,694 1410,550 1450,550')
    line('1410,694 1410,752 1450,752')
    line('1410,752 1410,954 1450,954')
    text(1090, 681, 'External HTTPS requests / responses', 'tiny')
    text(1450, 1085, 'No order execution', 'small')

    # Persistent files stay outside replaceable container filesystems.
    rect(450, 1170, 895, 185, '#ffffff', '#d9a14a')
    icon('ebs', 470, 1184, 48)
    text(547, 1215, 'Amazon EBS · persistent encrypted storage', 'heading')
    text(470, 1257, 'postgres_data: database     data/ + reports/: holdings and captures', 'body')
    text(470, 1287, '.secrets/: credentials     Caddy volumes: certificates and configuration', 'small')
    text(470, 1325, 'Retained when EC2 stops · container replacement does not delete records', 'small')
    line('1168,1065 1168,1170')
    line('650,1065 650,1170')
    text(666, 1152, 'Persistent volumes / bind mounts', 'small')

    rect(1430, 1170, 330, 185, '#f6fbf4', '#88ab6b', dashed=True)
    icon('s3', 1450, 1184, 48)
    text(1522, 1215, 'Amazon S3', 'heading')
    text(1450, 1257, 'Off-instance database backups', 'body')
    text(1450, 1287, 'pg_dump → private S3 bucket', 'small')
    badge(1450, 1310, 'BACKUP UPLOAD TO ADD', '#e7f1e1', '#466333', 285)
    line('1345,1260 1430,1260', True)

    text(40, 1432, 'Solid boundaries: existing local components or proposed AWS resource placement. Dashed boxes: components to add.', 'small')
    text(40, 1460, 'Purple dashed arrows: DNS lookup. Grey arrows: runtime traffic / persistence; dashed grey: deployment or backup transfer.', 'small')
    text(40, 1490, 'AWS deployment is a proposal. Today: app + PostgreSQL run locally. No Amplify, ECS, RDS, load balancer or NAT gateway required.', 'small')
    parts.append('</svg>')
    return ''.join(parts)


def main():
    content = render()
    (ROOT / 'docs/physical-architecture.svg').write_text(content, encoding='utf-8')
    (ROOT / 'reports').mkdir(exist_ok=True)
    (ROOT / 'reports/investment-architecture.svg').write_text(content, encoding='utf-8')
    print('Updated architecture SVGs')


if __name__ == '__main__':
    main()
