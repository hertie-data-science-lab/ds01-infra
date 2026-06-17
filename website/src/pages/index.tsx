import React from 'react';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';

// Landing page for the full DS01 documentation site. Uses Docusaurus <Link>
// so pillar links are baseUrl-aware (correct under both the /ds01-infra/ GitHub
// Pages subpath and the Cloudflare preview root).

const pillars = [
  {
    to: '/guide',
    title: 'User Guide',
    desc: 'For researchers and students: getting started, daily workflows, GPU usage, scripting, and troubleshooting.',
  },
  {
    to: '/admin',
    title: 'Admin & Ops',
    desc: 'For maintainers: architecture, installation, system configuration, monitoring, maintenance, and security.',
  },
  {
    to: '/develop',
    title: 'Developer',
    desc: 'For contributors: development setup, contributing guide, and pointers into the subsystem references.',
  },
];

export default function Home(): JSX.Element {
  return (
    <Layout
      title="DS01 Documentation"
      description="Full documentation for the DS01 multi-user GPU container platform.">
      <main className="container margin-vert--lg">
        <h1>DS01 Documentation</h1>
        <p>
          The complete documentation for <strong>DS01</strong> — Hertie Data Science
          Lab's multi-user GPU container platform. Pick the track that fits you.
        </p>
        <div className="pillarGrid">
          {pillars.map((p) => (
            <Link key={p.to} className="pillarCard" to={p.to}>
              <h3>{p.title}</h3>
              <p>{p.desc}</p>
            </Link>
          ))}
        </div>
        <p>
          Looking for just the user guide? The public end-user site lives at{' '}
          <Link to="https://hertie-data-science-lab.github.io/ds01/">
            hertie-data-science-lab.github.io/ds01
          </Link>
          .
        </p>
      </main>
    </Layout>
  );
}
