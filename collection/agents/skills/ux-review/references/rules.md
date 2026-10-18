# ux-review — руллсет (цитовані UX-правила)

Формат кожного правила: `[категорія] НАЗВА — принцип → ЯК ПЕРЕВІРИТИ / що є порушенням → джерело(URL)`.
Поле **ЯК ПЕРЕВІРИТИ обов'язкове**: правило без спостережуваного чека в звіт не йде.

Пороги, що РІЗНЯТЬСЯ між джерелами (назви обидва, не вигадуй єдиний):
- **Тач-таргет:** WCAG 2.2 min 24×24 CSS px (AA, 2.5.8) · WCAG enhanced 44×44 (AAA, 2.5.5) · Apple HIG 44×44 pt · Material 48×48 dp + 8 dp проміжок. Застосовуй за контекстом (тач-первинна дія → 44/48; щільна таблиця на десктопі → 24 з проміжком).
- **Час відгуку — різні прилади:** 0.1 s = відчуття миттєвості · **0.4 s (Doherty)** = цільова інтерактивність · 1 s = межа безперервності думки · 10 s = межа уваги (далі обов'язковий % прогрес). Не плутай 400 ms-ціль із 1 s/10 s-порогами.
- **Zoom — два критерії:** 1.4.4 Resize Text = текст до 200% без втрат · 1.4.10 Reflow = без 2-вимірного скролу при 400% (еквів. 320 CSS px). Перевіряй обидва, не змішуй.

---

## 1. Nielsen 10 Usability Heuristics
джерело на всі 10: https://www.nngroup.com/articles/ten-usability-heuristics/

[heuristic] Visibility of system status — система своєчасно повідомляє, що відбувається → порушення: дія без loading/підтвердження/зміни стану; нема «збережено/надіслано».
[heuristic] Match system & real world — мова користувача, знайомі поняття, природний порядок → порушення: внутрішній жаргон, коди, терміни розробника в UI.
[heuristic] User control & freedom — явний «аварійний вихід»: undo/cancel/back → порушення: незворотні дії без undo, модалка без закриття, пастки флоу.
[heuristic] Consistency & standards — однакові слова/дії = одне; конвенції платформи → порушення: кнопка діє по-різному на різних екранах, нестандартні іконки/терміни.
[heuristic] Error prevention — запобігати краще, ніж повідомляти → порушення: деструктивна дія без підтвердження/обмежень; вільне поле там, де має бути вибір.
[heuristic] Recognition over recall — робити опції видимими, не змушувати пам'ятати → порушення: треба пам'ятати дані з попереднього екрана; приховані вимоги.
[heuristic] Flexibility & efficiency — акселератори для досвідчених, не заважаючи новачкам → порушення: нема шорткатів/дефолтів/повтору частих дій.
[heuristic] Aesthetic & minimalist design — без зайвого, що конкурує з важливим → порушення: захаращення, декор, що відволікає від задачі.
[heuristic] Help users with errors — помилки звичайною мовою, точна проблема + рішення → порушення: криптичний код без пояснення й шляху виправлення.
[heuristic] Help & documentation — ідеально без довідки; за потреби — легко знайти, по задачі, конкретні кроки → порушення: довідку важко знайти/вона відірвана від контексту.

## 2. Laws of UX
[law] Jakob's Law — користувач очікує, що твій продукт працює як інші, знайомі → порушення: нестандартні патерни там, де є усталена конвенція → https://lawsofux.com/jakobs-law/
[law] Fitts's Law — час до цілі залежить від відстані й розміру → порушення: малі далекі клік-таргети; головну дію сховано/зменшено → https://lawsofux.com/fittss-law/
[law] Hick's Law — час рішення росте з кількістю/складністю виборів → порушення: довгі меню/безліч рівнорядних опцій без групування/дефолту → https://lawsofux.com/hicks-law/
[law] Miller's Law — у робочій пам'яті ~7±2 елементи → порушення: довгі негруповані списки/поля; розбивай на чанки → https://lawsofux.com/millers-law/
[law] Postel's Law — ліберально до вводу, суворо до виводу → порушення: відкидати валідний ввід через формат (пробіли в картці/телефоні) → https://lawsofux.com/postels-law/
[law] Tesler's Law — незнижувана складність; хтось її бере → порушення: неусувну складність перекладено на користувача замість системи → https://lawsofux.com/teslers-law/
[law] Peak-End Rule — досвід судять за піком і фіналом → порушення: болісний пік (помилка) чи кінцівка (оплата/confirmation) без турботи → https://lawsofux.com/peak-end-rule/
[law] Aesthetic-Usability Effect — естетичне сприймають як зручніше → порушення: неохайний візуал знижує довіру й толерантність до дрібних проблем → https://lawsofux.com/aesthetic-usability-effect/
[law] Doherty Threshold — продуктивність зростає при взаємодії <400 ms → порушення: відгук UI >400 ms без оптимістичного апдейту/feedback → https://lawsofux.com/doherty-threshold/
[law] Law of Proximity — близькі об'єкти = група → порушення: лейбл далі від свого поля, ніж від чужого; дії не згруповані → https://lawsofux.com/proximity/
[law] Law of Common Region — спільна межа/фон групує → порушення: пов'язані елементи без спільного контейнера/картки → https://lawsofux.com/common-region/
[law] Serial Position Effect — краще пам'ятають перший і останній → порушення: ключові нав-пункти/дії заховані в середині → https://lawsofux.com/serial-position-effect/
[law] Zeigarnik Effect — незавершені задачі пам'ятають краще → порушення: нема прогрес-індикатора/чеклиста для багатокрокового флоу → https://lawsofux.com/zeigarnik-effect/
[law] Von Restorff (Isolation) Effect — відмінний елемент запам'ятовують → порушення: кілька «primary» CTA конкурують; головну дію візуально не виділено → https://lawsofux.com/von-restorff-effect/

## 3. WCAG 2.2 (UX-дотичні SC)
[wcag] 2.5.8 Target Size (Min) AA — таргети ≥24×24 CSS px або достатній проміжок → порушення: <24px клік-таргет без spacing/inline/UA/essential-винятку → https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html
[wcag] 2.5.5 Target Size (Enhanced) AAA — таргети ≥44×44 CSS px → порушення (AAA): нижче 44px для основних дій → https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html
[wcag] 2.4.7 Focus Visible AA — видимий індикатор фокуса → порушення: outline:none без заміни; фокус не видно → https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html
[wcag] 2.4.11 Focus Not Obscured (Min) AA — сфокусований елемент хоча б частково видимий → порушення: sticky header/банер перекриває фокус → https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html
[wcag] 3.2.3 Consistent Navigation AA — повторювана навігація в однаковому порядку → порушення: нав-пункти міняють порядок/місце між сторінками → https://www.w3.org/WAI/WCAG22/Understanding/consistent-navigation.html
[wcag] 3.2.4 Consistent Identification AA — однофункційні компоненти ідентифіковані однаково → порушення: та сама дія названа/проіконена по-різному → https://www.w3.org/WAI/WCAG22/Understanding/consistent-identification.html
[wcag] 3.2.6 Consistent Help A — довідка/контакт у тому самому місці на всіх сторінках → порушення: посилання на допомогу «стрибає» → https://www.w3.org/WAI/WCAG22/Understanding/consistent-help.html
[wcag] 3.3.1 Error Identification A — помилкове поле визначене, помилка описана текстом → порушення: лише червона рамка без тексту; помилка тільки кольором → https://www.w3.org/WAI/WCAG22/Understanding/error-identification.html
[wcag] 3.3.3 Error Suggestion AA — якщо виправлення відоме — підкажи → порушення: «невірний формат» без прикладу правильного → https://www.w3.org/WAI/WCAG22/Understanding/error-suggestion.html
[wcag] 3.3.4 Error Prevention (Legal/Financial/Data) AA — зворотність / перевірка / підтвердження → порушення: незворотна оплата/видалення без confirm/review → https://www.w3.org/WAI/WCAG22/Understanding/error-prevention-legal-financial-data.html
[wcag] 3.3.6 Error Prevention (All) AAA — те саме для будь-якого сабміту → порушення (AAA): сабміт без зворотності/перевірки/підтвердження → https://www.w3.org/WAI/WCAG22/Understanding/error-prevention-all.html
[wcag] 1.4.3 Contrast (Min) AA — текст 4.5:1; великий (≥18pt/14pt bold) 3:1 → порушення: сірий текст нижче 4.5:1 → https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
[wcag] 1.4.11 Non-text Contrast AA — UI-компоненти/стани 3:1 до сусідніх кольорів → порушення: межа інпута/іконка/focus-ring нижче 3:1 → https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html
[wcag] 3.3.7 Redundant Entry A — не питати ту саму інфу двічі в межах сесії → порушення: повторне введення адреси/email без autofill/«те саме» → https://www.w3.org/WAI/WCAG22/Understanding/redundant-entry.html
[wcag] 3.3.8 Accessible Authentication (Min) AA — без когнітивного тесту для входу → порушення: заборона paste пароля; капча-головоломка без альтернативи → https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum.html
[wcag] 2.5.7 Dragging Movements AA — для drag — альтернатива одним pointer → порушення: reorder/slider лише перетягуванням без клік-альтернативи → https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html

## 4. Форми
[form] One thing per page — одне питання/рішення на сторінку (групуй лише там, де дослідження це підтверджує) → порушення: довга багатосекційна форма, де губиться фокус → https://design-system.service.gov.uk/patterns/question-pages/
[form] Label above field — постійний видимий лейбл над полем → порушення: лейбл зникає/зліва обрізає поле на мобільному → https://baymard.com/blog/mobile-form-usability-label-position
[form] Placeholder ≠ label — не використовувати placeholder замість лейбла → порушення: підказка зникає при вводі → провали пам'яті й виправлення помилок → https://www.nngroup.com/articles/form-design-placeholders/
[form] Inline validation — валідуй у правильний момент (на blur/після завершення поля, не на кожну літеру), помилку поруч із полем + підсвіти → порушення: помилки лише на сабміті або «на кожну літеру» → https://baymard.com/blog/inline-form-validation ; https://www.nngroup.com/articles/errors-forms-design-guidelines/
[form] Error wording — опиши, що сталось + як виправити; без жаргону/«please/sorry/you forgot» → порушення: «An error occurred»/«This field is required» без підказки → https://design-system.service.gov.uk/components/error-message/
[form] Error summary — зведи помилки вгорі з лінками на поля; той самий текст у summary й біля поля → порушення: нема навігації до першої помилки у довгій формі → https://design-system.service.gov.uk/components/error-message/
[form] Preserve input on error — не очищати поля при помилці → порушення: сабміт з помилкою стирає форму → https://design-system.service.gov.uk/components/error-message/
[form] Input types & autocomplete — правильний type/inputmode/autocomplete → порушення: email полем type=text без autocomplete; нема числової клавіатури → https://www.nngroup.com/articles/web-form-design/
[form] Destructive confirmation — деструктивні/фінансові/правові дії зворотні, перевірені або підтверджені → порушення: delete/pay одним кліком без confirm/undo → https://www.w3.org/WAI/WCAG22/Understanding/error-prevention-legal-financial-data.html
[form] Logical grouping — групуй пов'язані поля (proximity/common region) → порушення: поля в хаотичному порядку; лейбл ближче до чужого поля → https://lawsofux.com/proximity/

## 5. Таблиці / списки даних
[table] Numeric right-align — числа праворуч, бажано tabular/моно-цифри → порушення: числа ліворуч — важко порівнювати розряди → https://www.nngroup.com/articles/data-tables/
[table] Freeze headers — закріпити рядок-заголовок і колонку-ідентифікатор при скролі → порушення: при скролі губиться, що означає стовпець/рядок → https://www.nngroup.com/articles/data-tables/
[table] Row tracking — zebra/легкі межі/hover для утримання рядка → порушення: суцільне полотно без орієнтирів ока → https://www.nngroup.com/articles/data-tables/
[table] Human-readable first column — перша колонка = зрозумілий ідентифікатор, не auto-id → порушення: UUID/числовий ключ першим стовпцем → https://www.nngroup.com/articles/data-tables/
[table] Row/batch actions — дії через чекбокси + Select All; уникати hover-only меню → порушення: дії видно лише при наведенні мишею → https://www.nngroup.com/articles/data-tables/
[table] Filters/sort visible state — фільтри помітні + явна індикація активного фільтра/сортування → порушення: незрозуміло, що список відфільтровано/чому порожній → https://www.nngroup.com/articles/data-tables/
[table] Edit in side panel — редагування в немодальній бічній панелі, не в модалці, що ховає таблицю → порушення: модалка перекриває контекст інших рядків → https://www.nngroup.com/articles/data-tables/
[table] Narrow-screen strategy — на вузькому: горизонтальний скрол зі sticky-колонкою (ідентифікатор + дії) або stacked-картки, без обрізання → порушення: таблиця ламає лейаут/обрізана; дії зникають при h-скролі → https://www.nngroup.com/articles/mobile-tables/
[table] Empty/zero state — порожня таблиця пояснює, що тут буде, і дає дію → порушення: порожньо без пояснення (грузиться? помилка?) → https://www.nngroup.com/articles/empty-state-interface-design/

## 6. Навігація / IA
[nav] Single primary nav — одна основна навігація, стабільна між екранами → порушення: конкурентні нав-системи або нав, що змінює порядок → https://www.w3.org/WAI/WCAG22/Understanding/consistent-navigation.html
[nav] Current-state visibility — видно, де користувач зараз (active стан) → порушення: нема підсвітки поточного пункту/кроку → https://www.nngroup.com/articles/ten-usability-heuristics/
[nav] Breadcrumbs for depth — хлібні крихти на глибоких ієрархіях → порушення: глибокий розділ без шляху назад до рівнів → https://www.nngroup.com/articles/breadcrumbs/
[nav] Consistent identification — однакові дії названі/проіконені однаково → порушення: «Видалити» то кнопка, то іконка-кошик, то «Прибрати» → https://www.w3.org/WAI/WCAG22/Understanding/consistent-identification.html

## 7. Зворотний зв'язок і стани
[state] Loading threshold — <1s нічого; 1–10s спінер/скелетон; >10s прогрес-бар із % і можливістю перервати → порушення: спінер на <1s (мерехтіння) або голий екран на >10s → https://www.nngroup.com/articles/response-times-3-important-limits/
[state] Perceived latency — відгук <400ms або оптимістичне оновлення/негайний feedback → порушення: клік без реакції >400ms → https://lawsofux.com/doherty-threshold/
[state] Empty states instructive — порожній стан пояснює, що тут може бути, і дає дію → порушення: цілком порожній екран → плутанина → https://www.nngroup.com/articles/empty-state-interface-design/
[state] Error states actionable — що сталось + як виправити, поруч із причиною → порушення: загальне «Something went wrong» без наступного кроку → https://design-system.service.gov.uk/components/error-message/
[state] Success + undo — підтверджувати успіх; для деструктивних давати undo → порушення: мовчазний успіх; видалення без «Відмінити» → https://www.nngroup.com/articles/ten-usability-heuristics/
[state] Progress indicator >10s — довгі операції з % прогресу й оцінкою часу → порушення: нескінченний спінер на довгій операції → https://www.nngroup.com/articles/progress-indicators/

## 8. Контент / мікрокопі
[copy] Action-oriented buttons — лейбл кнопки = дія/результат (дієслово) → порушення: «OK/Submit/Yes» замість «Зберегти зміни/Видалити курс» → https://www.nngroup.com/articles/ten-usability-heuristics/
[copy] User's language — слова користувача, без жаргону й кодів → порушення: технічні терміни/внутрішні назви в UI → https://www.nngroup.com/articles/ten-usability-heuristics/
[copy] Consistent terminology — один термін на одне поняття по всьому продукту → порушення: «курс/програма/клас» як синоніми → https://www.w3.org/WAI/WCAG22/Understanding/consistent-identification.html
[copy] Predictability — лейбл/дія роблять те, що обіцяють → порушення: «Зберегти» також публікує; лінк веде не туди → https://lawsofux.com/jakobs-law/

## 9. Моб/тач/респонсив
[mobile] Touch target — ≥44×44 pt (Apple HIG) / ≥48×48 dp (Material); WCAG min 24px / AAA 44px — назвати застосовний поріг → порушення: іконка-кнопка 24px як основна дія на тач → https://developer.apple.com/design/human-interface-guidelines/accessibility ; https://m3.material.io/foundations/designing/structure
[mobile] Target spacing — достатній проміжок між таргетами (Material ~8dp) → порушення: щільні дрібні таргети → помилкові тапи → https://m3.material.io/foundations/designing/structure
[mobile] No 2D scroll (Reflow) — контент без горизонтального скролу при 400% (320 CSS px), крім винятків (таблиці/мапи) → порушення: широкий блок ламає viewport → https://www.w3.org/WAI/WCAG22/Understanding/reflow.html
[mobile] Resize text 200% — текст читабельний при збільшенні до 200% без втрат/перекриття → порушення: обрізання/накладання при 200% тексту → https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html

## 10. Когнітивне навантаження
[cog] Progressive disclosure — показувати лише потрібне зараз, решту розкривати на вимогу → порушення: усі опції/поля одразу на одному екрані → https://www.nngroup.com/articles/progressive-disclosure/
[cog] Smart defaults — розумні дефолти замість порожніх обов'язкових виборів → порушення: обов'язковий вибір без очевидного дефолту → https://lawsofux.com/hicks-law/
[cog] Recognition over recall — впізнавання замість пригадування (видимі опції, недавнє, автозаповнення) → порушення: треба пам'ятати код/назву з іншого екрана → https://www.nngroup.com/articles/ten-usability-heuristics/
[cog] Chunking 5±2 — групувати в блоки по ~5±2, не довгі негруповані списки → порушення: меню/форма з 15 рівнорядних пунктів без груп → https://lawsofux.com/millers-law/

## 11. Стани інтерактивних контролів
[states] Interaction-state matrix — кожен інтерактивний контрол визначає й візуально розрізняє rest / hover / active(pressed) / focus / disabled / loading → порушення: hover=rest; нема pressed-фідбеку; disabled не відрізнити від активного; loading без індикації → https://m3.material.io/foundations/interaction/states/overview
[states] Focus окремо від hover — видимий focus-стан для клавіатури, не лише hover для миші → порушення: hover є, focus нема (клавіатура «сліпа») → https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html
[states] Disabled пояснює причину — зрозуміло, ЧОМУ контрол недоступний (підказка/текст); краще не показувати недоступне, ніж мертвий сірий → порушення: сірий контрол без жодного пояснення → https://www.nngroup.com/articles/ten-usability-heuristics/
[states] Loading/pending на контролі — асинхронна дія показує pending на самому контролі (спінер / disabled-на-час), не «мертвий клік» → порушення: натиснув — жодної реакції, незрозуміло, чи триває → https://www.nngroup.com/articles/progress-indicators/

---

## Найавторитетніші джерела (для цитування)
- NN/g 10 Usability Heuristics — https://www.nngroup.com/articles/ten-usability-heuristics/
- NN/g Response-Time Limits — https://www.nngroup.com/articles/response-times-3-important-limits/
- NN/g Placeholders Are Harmful — https://www.nngroup.com/articles/form-design-placeholders/
- NN/g Data Tables / Mobile Tables — https://www.nngroup.com/articles/data-tables/ , https://www.nngroup.com/articles/mobile-tables/
- NN/g Empty States / Progressive Disclosure — https://www.nngroup.com/articles/empty-state-interface-design/ , https://www.nngroup.com/articles/progressive-disclosure/
- NN/g Breadcrumbs — https://www.nngroup.com/articles/breadcrumbs/
- Laws of UX — https://lawsofux.com/
- WCAG 2.2 (W3C Rec) + Understanding pages — https://www.w3.org/TR/WCAG22/
- GOV.UK Design System — https://design-system.service.gov.uk/
- Baymard Institute (form research) — https://baymard.com/blog/mobile-form-usability-label-position
- Apple HIG — https://developer.apple.com/design/human-interface-guidelines/ · Material 3 — https://m3.material.io/

Усі URL підтверджені fetch'ем станом на 2026-10-14 (мертвий `nngroup.com/articles/hicks-law/` замінено на lawsofux + NN/g progressive-disclosure).
