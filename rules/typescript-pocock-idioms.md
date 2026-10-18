---
title: Matt Pocock / TotalTypeScript — ідіоми (правила)
---

# 🧠 Matt Pocock / TotalTypeScript — ідіоми

> **Область дії: TypeScript.** Усе нижче — про систему типів TS, і поза `*.ts`/`*.tsx` предмета
> не має. У полірепо (Rust, Python, Go поруч із TS) ці ідіоми на не-TS частину **не поширюються**:
> знахідка «не використано `satisfies`» на `.rs`-файлі хибна за побудовою. Мірник прив'язується
> до мови стовпчиком «діє на» — `~/.agents/rules/repo-standards-manifest.md` §0.

> Дистиляція з deep-crawl `totaltypescript.com` (600 сторінок: workshops/tutorials/tips/blog) + OSS-репо (`tsconfig`, `ts-reset`, `shoehorn`). Кожне правило — з source-slug `totaltypescript.com/<slug>`. Джерело в репо: `reports/typescript-style/pocock-idioms.md`; house-style: `.ai/agent/32-typescript-style.md`.

## 🎯 Type-system ідіоми
- **`satisfies` > `as`** (`how-to-use-satisfies-operator`) — додати констрейнт БЕЗ втрати inference/звуження. `as` — лише на trust-boundaries.
- **Без `any`** (`any-considered-harmful`) — `any` вимикає перевірки → `unknown` + narrow. Легітимний виняток: generic-констрейнти `<T extends (...args: any[]) => any>` (там `unknown` ламає variance) — зі scoped `eslint-disable` + причина.
- **Enums → `as const` object + union** (`why-i-dont-like-typescript-enums`) — TS enums nominal/дивні. `const X = {...} as const; type X = (typeof X)[keyof typeof X]`.
- **Discriminated unions > «мішок optional-ів»** (`discriminated-unions-are-a-devs-best-friend`) — стани як `{status:'loading'} | {status:'error';error} | {status:'success';data}`; switch по дискримінанту з **exhaustive `never` default**.
- **Derive, не дублюй** (`deriving-vs-decoupling`) — `Pick`/`Omit`/`typeof`/indexed-access від SSOT; decouple лише коли звʼязок випадковий. Zod `z.infer` = основна деривація.
- **Branded types для id** (`four-essential-typescript-patterns`) — `type Password = Brand<string,'Password'>`; покрити КОЖЕН id.
- **`as never`** (`as-never`) — рідко, лише коли TS не може прослідкувати звуження union; документуй.
- **`type` за замовчуванням**, `interface` лише під `extends` (`type-vs-interface`). ⚠️ **Конфлікт із проєктом:** eslint форсує `interface` → у цьому репо свідома девіація (лишаємо `interface`).
- `Readonly`/`readonly` + immutable; `as const` для літералів.

## 🔧 Function / object
- **Не тип `Function`** (`dont-use-function-keyword`) — задавай `(item:T)=>number`; для truly-any → `(...args:any[])=>any`.
- **Без method-shorthand** (`method-shorthand-syntax-considered-harmful`) — `foo(p):void` bivariant (небезпечно) → property syntax `foo:(p)=>void` (`method-signature-style:'property'`).
- **Return-типи на top-level функціях** (`should-you-declare-return-types`) — для читачів+AI; **виняток: JSX-компоненти**.
- **Порядок пропсів впливає на inference** (`property-order-matters`) — producer перед consumer.
- Generics: реальні констрейнти, ніколи `<any>`; `NoInfer<>` блокує небажаний inference; `const` type-params для літералів; «немає такого як generic-тип» (є generic-функція).

## ⚛️ React
- Пропси — локальний `interface Props`/`type Props`, **колокейт** у файлі компонента.
- `React.ReactNode` для children (не `JSX.Element`); `ComponentProps<typeof X>` — позичити пропси; `ElementRef`/`ComponentRef` — refs.
- `React.FC` не обовʼязковий; return-тип компонента = JSX (без анотації).

## 🏗️ Архітектура / тести
- **Де тримати типи** (`where-to-put-your-types`) — single-use колокейт у файлі; спільні — підняти в модуль.
- **Тести типів** — `how-to-test-your-types`; **shoehorn `fromPartial`** для partial-моків (ніколи `as any` у тестах); скіл `migrate-to-shoehorn`.
- **`ts-reset`** — `fetch`/`JSON.parse`→`unknown`; `filter(Boolean)` звужує; `Array.isArray`→`unknown[]`. Імпорт один раз (app-only).
- **tsconfig** — `@total-typescript/tsconfig/bundler/dom/app` як база; наш MAX додає `exactOptionalPropertyTypes`, `noPropertyAccessFromIndexSignature`.

## 📌 Застосовано в cassiopeia-admin-ui (house decisions)
- ✅ no-enums (as const+union), satisfies>as, unknown-at-boundaries, discriminated unions, branded ids, Zod=SSOT.
- ✅ Deep modules / single source; **services лишаються класами** (не рефакторити у функції).
- ⚠️ Девіація: `interface` (не `type`-default) — форсовано eslint.
- Правила as-error глобально (ратчет): `.ai/rules/typescript-style.mdc`, initiative `project_typescript_pocock_initiative`.

## 🔗 Пов'язане
- Скіли: `tdd`, `migrate-to-shoehorn` (див. проєктний `Testing & Codemods` промт).
- Повний корпус у репо: `reports/typescript-style/` (pocock-idioms, ratchet-worklist, modal-service-audit); house-style `.ai/agent/32-typescript-style.md` + `.ai/rules/typescript-style.mdc`.
