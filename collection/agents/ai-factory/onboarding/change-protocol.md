# Additive зміна, повтор і guarded restore

[Вхід](../onboarding.md) · [Acceptance](acceptance-template.md)

Це протокол для вже авторизованого writer, не автоматична команда застосування. Preflight лишається read-only. Файли receipt/backup/diff зберігаються в task workspace, не в додатковому tracker репо. Повтор використовує той самий canonical adapter і entry marker/path.

## Перед записом

1. Inventory визначає один наявний authoritative entry та task workflow. Якщо adapter/pointer уже є, прочитай їх; не додавай ще один каталог, блок або копію правил. Семантичні дублікати перевіряються вручну, exact hash сам їх не знаходить.
2. Зафіксуй root, branch, HEAD, scoped dirty/untracked state. Обери explicit files, перевір resolved paths і відсутність symlink/secret/config targets. Для existing entry зміна — лише мінімальний pointer/узгодження описового факту. Нормативний конфлікт без owner-рішення не переписується.
3. Для кожного файла збережи receipt: absolute target, existed_before, baseline SHA256 (або null), byte-for-byte backup path (або null), proposed SHA256, diff, authorization/source, operation status. Backup включає вже наявні чужі dirty bytes; це не дозвіл переписати їх. Не записуй секрети в receipt.
4. Переглянь повний diff та незалежне review. Перед кожним записом повторно звір існування/тип/батьківські шляхи й SHA baseline. За будь-якої зміни — BLOCKED цього файла, не force overwrite. Під час короткого apply потрібне узгоджене вікно без конкурентного writer: hashguard не є OS-lock. Зберігай permissions existing файла. Записуй лише reviewed bytes, потім перевір applied SHA й познач receipt applied.
5. Після застосування перевір links/anchors, adapter compatibility та receipt. `adapter_files` у manifest містить canonical destinations і desired SHA: preflight має повернути NOOP для matching bytes. Different bytes → BLOCKED/reviewed merge; не автоматичний reapply. Не трактуй NOOP як semantic acceptance або runtime PASS.

## Restore лише власного застосованого diff

Restore потребує доручення в поточному scope; наявність backup сама не наказує відкотити роботу. Не використовуй git reset/checkout/clean або повний snapshot repo.

- Receipt має applied=true і applied SHA. Повторно перевір target type/path та **поточний SHA == applied SHA**. Якщо ні — BLOCKED, збережи конкурентну зміну; потрібен ручний merge з власником, не overwrite.
- Existing файл: перевір backup SHA == baseline SHA, віднови лише його байти/permissions, перевір baseline SHA. Новий файл: видали лише цей exact applied файл за guard; не видаляй теки рекурсивно й не прибирай сторонні файли.
- Partial apply: restore лише записані applied entries; untouched files не чіпати. Запиши per-file restore result; не називай transaction атомарною між багатьма файлами.
- Повтор restore: baseline уже відновлено або own new file уже відсутній → NOOP. Інший content → BLOCKED. Backup/receipt зберігаються як докази.

Мінімальна disposable rehearsal: add → повтор NOOP; existing merge зі збереженням owner bytes; concurrent edit → apply/restore BLOCKED; own applied bytes → baseline restore; new file → exact removal; повтор restore NOOP. Це перевірка протоколу на fixtures, не дозвіл працювати з іншими репо.
