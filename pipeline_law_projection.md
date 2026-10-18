# pipeline_law_projection — conditional legal guidance and archived projection

`config/rules_legal.yaml` is the source of conditional class-to-rule mappings, official URLs,
requirements, and limitations. Sections 2 and 5 are generated from that catalogue; change the
YAML and run `scripts/render_law_projection.py`, or use `--check` to detect drift.
The taxonomy helps organize observations; it does not determine a verdict by itself.

Sections 3 and 4 (a per-clip worksheet projection) are omitted from this public copy.
Historical `L-xx` IDs remain archived references; executable selection uses catalogue `rule_id` values.

---

## 1. Columns

The per-clip projection table (sections 3–4) is not part of the public copy: it was derived from
the organisers' clip labels, which may not be published.

---

## 2. Conditional classification guidance (generated)

<!-- GENERATED: law-classifications:start -->
Generated from `config/rules_legal.yaml`; edit the catalogue and run `.venv/bin/python scripts/render_law_projection.py`. A class is a candidate, never a fixed verdict.

| Class | Name / candidate code | Candidate rule and official source | Status | Conditions | Limitations |
|---|---|---|---|---|---|
| **V1** | Возможное отсутствие идентификации / `ID` | `CASH_ID_IN` — 19 пп. 1) ([official source](https://adilet.zan.kz/rus/docs/V1900019680)); `CASH_ID_OUT` — 31 пп. 1) ([official source](https://adilet.zan.kz/rus/docs/V1900019680)) | conditional | Установить прием или выдачу наличных и применимую процедуру.; Проверить весь эпизод, ранее выполненную идентификацию и цифровые документы. | Отсутствие бумажного удостоверения в кадре недостаточно; лица не распознавать. |
| **V1b** | Возможное несоответствие процедуры идентификации / `THIRD` | `CASH_ID_IN` — 19 пп. 1) ([official source](https://adilet.zan.kz/rus/docs/V1900019680)); `CASH_ID_OUT` — 31 пп. 1) ([official source](https://adilet.zan.kz/rus/docs/V1900019680)) | conditional | Подтвердить, чья идентификация требуется и какие действия выполнены, без распознавания лиц. | Передача документа другим человеком не устанавливает его владельца или отсутствие законного представительства. |
| **V2** | Деньги предыдущей операции вне хранения / `TABLE` | `CASH_STORAGE` — 20 ([official source](https://adilet.zan.kz/rus/docs/V1900019680)) | conditional | Проследить деньги завершенной операции и отличить их от денег текущего клиента. | Совместная видимость нескольких пачек не доказывает смешивание клиентов. |
| **V3** | Принятые наличные оставлены вне устройства хранения / `TABLE` | `CASH_STORAGE` — 20 ([official source](https://adilet.zan.kz/rus/docs/V1900019680)) | conditional | Подтвердить завершение операции и статус денег как ранее принятых; видны место хранения и уход. | Не подменять хранением текущую рабочую обработку денег; сам уход не подтверждает все условия. |
| **V4** | Возможное несоблюдение хранения в кассовом устройстве / `SAFE` | `CASH_STORAGE` — 20 ([official source](https://adilet.zan.kz/rus/docs/V1900019680)) | conditional | Различить устройство на рабочем месте и кладовую/сейфовую комнату; установить хранение ранее принятых денег. | Открытие для операции допустимо; состояние замка нельзя угадать. Пункты о кладовой не применять автоматически к ящику кассира. |
| **V5** | Возможное нарушение обращения с ключами / `KEYS` | `CASH_KEYS` — 76, 80 ([official source](https://adilet.zan.kz/rus/docs/V1900019680)) | conditional | Установить назначение ключа, ответственного и применимый порядок хранения. | Не считать любой похожий предмет ключом; требования к кладовой и кассовому устройству различаются. |
| **V6** | Прием или пересчет без присутствия клиента / `INCOMPLETE` | `CASH_PRESENT` — 20, абз. 1 ([official source](https://adilet.zan.kz/rus/docs/V1900019680)) | conditional | Подтвердить прием/пересчет именно денег клиента и фактический уход до завершения. | Отличать от внутреннего пересчета и отсутствия клиента только в ракурсе камеры. |
| **V7** | Уход до окончания обслуживания / `LEAVE` | `CASH_LEAVE` — 22 ([official source](https://adilet.zan.kz/rus/docs/V1900019680)) | conditional | Подтвердить фактический уход с рабочего места при незавершенном обслуживании того же клиента. | Вставание, движение внутри места или уход после завершения не достаточны. |
| **V8** | Хранение личных вещей в кассовом узле / `PERSONAL` | `CASH_PERSONAL` — 12 ([official source](https://adilet.zan.kz/rus/docs/V1900019680)) | conditional | Подтвердить личную принадлежность, хранение и нахождение в кассовом узле. | Учитывать лекарства, медицинские изделия и разрешенные средства связи без фото-/видеофиксации; функции устройства не угадывать. |
| **V9** | Возможное отсутствие пересчета или несоответствие оборудования / `NOCOUNT` | `CASH_COUNT` — 19 пп. 2) ([official source](https://adilet.zan.kz/rus/docs/V1900019680)); `CASH_EQUIPMENT` — 41 ([official source](https://adilet.zan.kz/rus/docs/V1900019680)) | conditional | Раздельно проверить полный процесс приема банкнот и технические требования к оборудованию. | Отсутствие видимой машины не равно отсутствию пересчета; характеристики оборудования требуют внешних сведений. |
| **V10** | Возможное несоблюдение обращения с сомнительными банкнотами / `REJECT` | `CASH_SUSPECT` — 57, 59 ([official source](https://adilet.zan.kz/rus/docs/V1900019680)) | conditional | Независимо подтвердить статус сомнительных банкнот и проследить их дальнейшую обработку. | Отбраковка машиной не равна сомнительности или подделке; не утверждать неисполнение экспертизы по короткому эпизоду. |
| **V11** | Возможное несоответствие входа кассы / `DOOR` | `PREMISES_ACCESS` — 8; 16 пп. 1) ([official source](https://adilet.zan.kz/rus/docs/V2000020075)) | conditional | Подтвердить назначение помещения и входа, условия изоляции и доступа. | Норма об оборудовании запираемой дверью не означает запрета любого открытия; п. 16 до 01.01.2027 действует во временной редакции. |
| **V12** | Частичный возврат наличных — наблюдение для проверки / `CASH_RETURN` | No confirmed direct rule — review only | observation_only | Установить вид операции, ее стадию и причину возврата; запросить недостающие сведения. | Возврат части суммы сам по себе не запрещен указанными общими процедурами. Не назначать закон по формуле «не соответствует ни приему, ни выдаче». Не формировать нарушение только из этой метки. |
| **V13** | Оставленные документы или предметы / `UNATTENDED_ITEMS` | `CASH_KEYS` — 76, 80 ([official source](https://adilet.zan.kz/rus/docs/V1900019680)); `IS_PAPER_PROTECTION` — 76 ([official source](https://adilet.zan.kz/rus/docs/V2600038336)) | conditional | Подтвердить конкретную природу предмета: ключи/регулируемые ценности или бумага с защищаемыми данными; проверить банковский порядок. | Любая сумка, журнал или лист не являются автоматически регулируемыми ценностями. Для бумаги нужен информационный контекст. |
| **V14** | Возможное отсутствие завершения или блокировки сеанса / `EXIT` | `IS_SESSION_TIMEOUT` — 71 пп. 9); 72 ([official source](https://adilet.zan.kz/rus/docs/V2600038336)) | records_required | Подтвердить более 30 минут неактивности и отсутствие как завершения сеанса, так и блокировки.; Проверить применимость пункта 71 и исключения пункта 72 с использованием сведений системы. | Короткий уход и включенный экран недостаточны. Не утверждать нарушение неизвестного внутреннего регламента. |

<!-- GENERATED: law-classifications:end -->

---

## 3. Projection table (verdict from pipeline)

Removed from the public copy (per-clip labels and findings from the organisers' dataset).

---

## 4. Class frequency in the training set (by pipeline verdict)

Removed from the public copy (derived from the same labels).

---

## 5. Conditional `description` assembly (generated)

<!-- GENERATED: law-description:start -->
1. Describe only the observation at `timecode_sec`; keep each event and its evidence separate.
2. Map the class through the generated table to a candidate `type_code` and `rule_id`.
3. Check classification conditions and limitations, then the selected rule's `required_observations`, `limitations`, and `evidence_mode` in the catalogue. A candidate rule is not proof of applicability; missing records must not be invented.
4. Only after context checks, append the selected catalogue citation, applicability limits, and official URL. Pending references remain possible grounds requiring review. No confirmed rule means an observation for review without an asserted legal violation.
5. Preserve multiple independent events and 1–3 evidence frames per event. Do not derive a new-video verdict from historical worksheet labels or this document's archived rows.

Public schema stays unchanged: `type`, `timecode_sec`, `description`, `evidence_frames`. The backend appends verified catalogue citation text to `description`; it does not generate legal text or validate context automatically.

Never invent amounts, postings, banknote authenticity, identity/document ownership, internal-bank policy, or criminal intent. No face identification or audio analysis. No dataset or observations are sent to government sites.

<!-- GENERATED: law-description:end -->
