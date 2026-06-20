import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

// Full ds01-infra documentation site. Three audience pillars, each a
// plugin-content-docs instance with its own sidebar + navbar dropdown:
//   ../docs/user     -> /guide     (end-user; also published standalone via ds01-hub)
//   ../docs/admin    -> /admin     (evergreen admin/ops; ephemeral docs excluded below)
//   ../docs/develop  -> /develop   (contributor docs; links out to in-repo READMEs)
//
// Content lives in sibling dirs at the repo root; this Docusaurus instance
// lives in website/ and points each plugin at ../<dir>.

const EDIT_BASE = 'https://github.com/hertie-data-science-lab/ds01-infra/edit/main';

const config: Config = {
  title: 'DS01 Documentation',
  tagline: 'Multi-user GPU container platform — full documentation',

  future: {v4: true},

  // baseUrl defaults to the GH Pages project subpath
  // (hertie-data-science-lab.github.io/ds01-infra/); override with
  // DOCUSAURUS_BASE_URL=/ for hosts that serve at root (Cloudflare previews).
  url: 'https://hertie-data-science-lab.github.io',
  baseUrl: process.env.DOCUSAURUS_BASE_URL ?? '/ds01-infra/',

  organizationName: 'hertie-data-science-lab',
  projectName: 'ds01-infra',

  onBrokenLinks: 'throw',
  onBrokenMarkdownLinks: 'throw',

  markdown: {
    format: 'md',
    mermaid: true,
  },

  themes: ['@docusaurus/theme-mermaid'],

  i18n: {defaultLocale: 'en', locales: ['en']},

  presets: [
    [
      'classic',
      {
        // The User pillar is the preset's docs instance (id 'default') — the
        // local-search SearchBar resolves the 'default' docs instance, so one
        // pillar must hold that id. Admin + Developer are plugins below.
        docs: {
          path: '../docs/user',
          routeBasePath: 'guide',
          sidebarPath: './sidebarsUser.ts',
          editUrl: `${EDIT_BASE}/docs/user/`,
          // docs/user/ has both README.md and index.md at root (Docusaurus
          // treats both as the folder index -> collision). Keep index.md as
          // the pillar landing; README.md stays for GitHub repo browsing only.
          exclude: ['README.md'],
        },
        blog: false,
        theme: {customCss: './src/css/custom.css'},
      } satisfies Preset.Options,
    ],
  ],

  plugins: [
    [
      '@docusaurus/plugin-content-docs',
      {
        id: 'admin',
        path: '../docs/admin',
        routeBasePath: 'admin',
        sidebarPath: './sidebarsAdmin.ts',
        editUrl: `${EDIT_BASE}/docs/admin/`,
        // Publish evergreen admin docs only. Ephemeral working docs
        // (planning logs, point-in-time audits, completed-migration incident
        // reports) are excluded rather than moved.
        exclude: [
          'planning/**',
          'audits/**',
          'CONTAINER-CONSISTENCY-FIXES.md',
          'gpu-allocation-implementation.md',
          'docker-permissions-migration.md',
          'huy_simon_report.md',
        ],
      },
    ],
    [
      '@docusaurus/plugin-content-docs',
      {
        id: 'develop',
        path: '../docs/develop',
        routeBasePath: 'develop',
        sidebarPath: './sidebarsDevelop.ts',
        editUrl: `${EDIT_BASE}/docs/develop/`,
      },
    ],
    [
      require.resolve('@easyops-cn/docusaurus-search-local'),
      {
        hashed: true,
        language: ['en'],
        docsDir: ['../docs/user', '../docs/admin', '../docs/develop'],
        docsRouteBasePath: ['guide', 'admin', 'develop'],
        indexBlog: false,
      },
    ],
  ],

  themeConfig: {
    colorMode: {respectPrefersColorScheme: true},
    navbar: {
      title: 'DS01 Docs',
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'userSidebar',
          label: 'User Guide',
          position: 'left',
        },
        {
          type: 'docSidebar',
          docsPluginId: 'admin',
          sidebarId: 'adminSidebar',
          label: 'Admin & Ops',
          position: 'left',
        },
        {
          type: 'docSidebar',
          docsPluginId: 'develop',
          sidebarId: 'developSidebar',
          label: 'Developer',
          position: 'left',
        },
        {
          href: 'https://hertie-data-science-lab.github.io/ds01/',
          label: 'End-user site',
          position: 'right',
        },
        {
          href: 'https://github.com/hertie-data-science-lab/ds01-infra',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            {label: 'User Guide', to: '/guide'},
            {label: 'Admin & Ops', to: '/admin'},
            {label: 'Developer', to: '/develop'},
          ],
        },
        {
          title: 'More',
          items: [
            {label: 'End-user site', href: 'https://hertie-data-science-lab.github.io/ds01/'},
            {label: 'Issue tracker', href: 'https://github.com/hertie-data-science-lab/ds01-hub/issues'},
            {label: 'GitHub', href: 'https://github.com/hertie-data-science-lab/ds01-infra'},
          ],
        },
      ],
      copyright: `Hertie Data Science Lab — DS01.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'docker', 'yaml', 'python', 'json'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
