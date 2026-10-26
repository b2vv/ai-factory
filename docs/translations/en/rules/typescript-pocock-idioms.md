---
title: Matt Pocock / TotalTypeScript — idioms (rules)
---

> **Historical English translation — authored derivative.** Original: [rules/typescript-pocock-idioms.md](../../../../rules/typescript-pocock-idioms.md). Original SHA256: `06b659fe1b25ea31bd57b093b48646270ac08b05320798be4f50c94884266c42`. Source base: `2c0960885926075502a319a19eafbed901690dde`. The original is unchanged. Historical assertions, statuses, examples, and limitations are retained; this translation does not establish current policy, execution evidence, or activation. Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retained.

# 🧠 Matt Pocock / TotalTypeScript — idioms

> **Scope: TypeScript.** Everything below concerns the TS type system and has no subject
> outside `*.ts`/`*.tsx`. In a polyrepo (Rust, Python, Go alongside TS), these idioms **do not apply**
> to the non-TS portion: a finding that a `.rs` file “does not use `satisfies`” is invalid by construction.
> The yardstick is bound to the language through the “applies to” column — `~/.agents/rules/repo-standards-manifest.md` §0.

> Distilled from a deep crawl of `totaltypescript.com` (600 pages: workshops/tutorials/tips/blog) + OSS repositories (`tsconfig`, `ts-reset`, `shoehorn`). Each rule includes a source slug `totaltypescript.com/<slug>`. Repository source: `reports/typescript-style/pocock-idioms.md`; house style: `.ai/agent/32-typescript-style.md`.

## 🎯 Type-system idioms
- **`satisfies` > `as`** (`how-to-use-satisfies-operator`) — add a constraint WITHOUT losing inference/narrowing. Use `as` only at trust boundaries.
- **No `any`** (`any-considered-harmful`) — `any` disables checks → `unknown` + narrow. A legitimate exception: generic constraints `<T extends (...args: any[]) => any>` (where `unknown` breaks variance) — with a scoped `eslint-disable` + reason.
- **Enums → `as const` object + union** (`why-i-dont-like-typescript-enums`) — TS enums are nominal/odd. `const X = {...} as const; type X = (typeof X)[keyof typeof X]`.
- **Discriminated unions > “a bag of optionals”** (`discriminated-unions-are-a-devs-best-friend`) — states as `{status:'loading'} | {status:'error';error} | {status:'success';data}`; switch on the discriminant with an **exhaustive `never` default**.
- **Derive, do not duplicate** (`deriving-vs-decoupling`) — `Pick`/`Omit`/`typeof`/indexed-access from the SSOT; decouple only when the connection is incidental. Zod `z.infer` = the primary derivation.
- **Branded types for IDs** (`four-essential-typescript-patterns`) — `type Password = Brand<string,'Password'>`; cover EVERY ID.
- **`as never`** (`as-never`) — rarely, only when TS cannot track union narrowing; document it.
- **`type` by default**, `interface` only for `extends` (`type-vs-interface`). ⚠️ **Project conflict:** eslint forces `interface` → this repository makes a deliberate deviation (keep `interface`).
- `Readonly`/`readonly` + immutable; `as const` for literals.

## 🔧 Function / object
- **Not the `Function` type** (`dont-use-function-keyword`) — specify `(item:T)=>number`; for truly-any → `(...args:any[])=>any`.
- **No method shorthand** (`method-shorthand-syntax-considered-harmful`) — `foo(p):void` is bivariant (unsafe) → property syntax `foo:(p)=>void` (`method-signature-style:'property'`).
- **Return types on top-level functions** (`should-you-declare-return-types`) — for readers + AI; **exception: JSX components**.
- **Property order affects inference** (`property-order-matters`) — producer before consumer.
- Generics: real constraints, never `<any>`; `NoInfer<>` blocks unwanted inference; `const` type parameters for literals; “there is no such thing as a generic type” (there is a generic function).

## ⚛️ React
- Props — local `interface Props`/`type Props`, **colocate** in the component file.
- `React.ReactNode` for children (not `JSX.Element`); `ComponentProps<typeof X>` to borrow props; `ElementRef`/`ComponentRef` for refs.
- `React.FC` is optional; a component's return type = JSX (without an annotation).

## 🏗️ Architecture / tests
- **Where to keep types** (`where-to-put-your-types`) — colocate single-use types in the file; lift shared ones into the module.
- **Type tests** — `how-to-test-your-types`; **shoehorn `fromPartial`** for partial mocks (never `as any` in tests); the `migrate-to-shoehorn` skill.
- **`ts-reset`** — `fetch`/`JSON.parse`→`unknown`; `filter(Boolean)` narrows; `Array.isArray`→`unknown[]`. Import once (app-only).
- **tsconfig** — `@total-typescript/tsconfig/bundler/dom/app` as the base; our MAX adds `exactOptionalPropertyTypes`, `noPropertyAccessFromIndexSignature`.

## 📌 Applied in cassiopeia-admin-ui (house decisions)
- ✅ no-enums (as const+union), satisfies>as, unknown-at-boundaries, discriminated unions, branded ids, Zod=SSOT.
- ✅ Deep modules / single source; **services remain classes** (do not refactor them into functions).
- ⚠️ Deviation: `interface` (not `type`-default) — enforced by eslint.
- Rules as errors globally (ratchet): `.ai/rules/typescript-style.mdc`, initiative `project_typescript_pocock_initiative`.

## 🔗 Related
- Skills: `tdd`, `migrate-to-shoehorn` (see the project's `Testing & Codemods` prompt).
- Full corpus in the repository: `reports/typescript-style/` (pocock-idioms, ratchet-worklist, modal-service-audit); house style `.ai/agent/32-typescript-style.md` + `.ai/rules/typescript-style.mdc`.
