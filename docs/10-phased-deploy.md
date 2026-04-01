# Пошаговое развёртывание (по этапам)

Инструкция для постепенного вывода продакшена в таком порядке:

1. **Этап A** — `nl-ams-1` (foreign exit) и `ru-msk-1` (RU relay).
2. **Этап B** — `nl-ams-2`, `de-fra-1` (foreign) и `ru-msk-3` (RU).
3. **Этап C** — стек Telegram-бота на `nl-ams-1` и мониторинг (Prometheus + Grafana) на `de-fra-1`.

Предполагается, что инвентарь и `configs/production/vars/servers.yml` уже описывают **все** будущие ноды (как в репозитории), а секреты заполнены в Vault для **всех** IP и ключей. На ранних этапах Ansible ограничивается флагом **`--limit`**, чтобы не трогать серверы, которые ещё не готовы.

Общие требования к машине оператора и Vault — в [02-first-deploy.md](02-first-deploy.md).

---

## Перед любым этапом

Из корня репозитория:

```bash
ansible-galaxy collection install -r requirements.yml   # один раз
make ensure-vault-link
export ANSIBLE_CONFIG=ansible.cfg   # если не задан по умолчанию
# при шифрованном vault:
export ANSIBLE_VAULT_PASSWORD_FILE=.vault_pass
```

Дальше команды приведены с `ansible-playbook`; при необходимости добавьте `--vault-password-file` или `-e @extra.yml`.

---

## Этап A — `nl-ams-1` и `ru-msk-1`

Цель: поднять первый foreign exit и первый RU relay; между ними уже может работать туннель и балансировщик (остальные foreign в конфиге пока могут быть недоступны — это ожидаемо до этапа B).

1. Убедитесь, что SSH до **`nl-ams-1`** и **`ru-msk-1`** работает под пользователем из `inventories/production/group_vars/all/common.yml`.
2. Разверните foreign только на `nl-ams-1`:

   ```bash
   ansible-playbook playbooks/deploy-foreign-exit.yml --limit nl-ams-1
   ```

3. Разверните RU relay только на `ru-msk-1`:

   ```bash
   ansible-playbook playbooks/deploy-ru-relay.yml --limit ru-msk-1
   ```

Проверки: на обоих хостах контейнер `xray` в `docker ps`; на RU слушает inbound (см. `xray_inbound_port` в `configs/production/vars/xray.yml`).

**Мониторинг и Telegram в этот момент не ставятся** — Prometheus ещё не скрапит ноды, это нормально.

---

## Этап B — `nl-ams-2`, `de-fra-1`, `ru-msk-3`

Цель: добавить оставшиеся foreign (включая будущий хост Prometheus/Grafana) и второй RU relay.

1. Foreign на `nl-ams-2` и `de-fra-1`:

   ```bash
   ansible-playbook playbooks/deploy-foreign-exit.yml --limit nl-ams-2,de-fra-1
   ```

2. RU relay на `ru-msk-3`:

   ```bash
   ansible-playbook playbooks/deploy-ru-relay.yml --limit ru-msk-3
   ```

После этого полный набор нод из `servers.yml` должен быть развёрнут с точки зрения VPN.

---

## Этап C — Telegram и мониторинг

Цель: бот и БД на **`nl-ams-1`**, стек Prometheus + Grafana (+ Caddy) на **`de-fra-1`**. Их лучше включать, когда все VPN-ноды из этапов A–B уже подняты: в `prometheus.yml` перечислены все адреса из `servers.yml`, а UFW на нодах открывает порты экспортёров только с IP **`de-fra-1`** (`vault_de_fra_1_ip`).

### 1. Telegram-бот (включая user-mapping exporter)

На `nl-ams-1`:

```bash
make deploy-telegram
# или явно:
ansible-playbook playbooks/deploy-telegram-bot.yml
```

Убедитесь, что выполнены DNS и поля Vault для бота и подписки (см. [06-bot-and-subs.md](06-bot-and-subs.md)).

### 2. Внешнее API подписки на RU (если используете)

После бота, когда нужны публичные прокси подписки на релеях:

```bash
make deploy-subscription-external
```

### 3. Мониторинг на `de-fra-1`

```bash
make deploy-monitoring
# или:
ansible-playbook playbooks/deploy-monitoring.yml
```

Перед этим: A-запись для `vault_grafana_domain` на IP `de-fra-1`, порты и пароли Grafana в Vault — см. [05-monitoring.md](05-monitoring.md).

После деплоя проверьте цели Prometheus (`/-/targets` или API) и Grafana по HTTPS на `grafana_https_port` (по умолчанию **8443**).

---

## Порядок make-таргетов (сводка)

| Этап | Действие |
|------|----------|
| A | `deploy-foreign-exit.yml --limit nl-ams-1` → `deploy-ru-relay.yml --limit ru-msk-1` |
| B | `deploy-foreign-exit.yml --limit nl-ams-2,de-fra-1` → `deploy-ru-relay.yml --limit ru-msk-3` |
| C | `make deploy-telegram` → при необходимости `make deploy-subscription-external` → `make deploy-monitoring` |

Полный прогон без limit (когда все серверы готовы одновременно) по-прежнему описан в [02-first-deploy.md](02-first-deploy.md) (`make deploy-vpn`, `make deploy-full` и т.д.).

---

## Замечания

- **`--limit`** не меняет `servers.yml`: списки релеев и foreign для бота/конфигов Xray остаются полными; ограничивается только набор хостов, куда Ansible подключается в данном прогоне.
- Пока не развёрнут **`de-fra-1`**, не запускайте **`deploy-monitoring`**: Prometheus и так негде размещать; после появления хоста выполните этап C.
- Если временно выключаете часть хостов из инвентаря вместо `limit`, синхронизируйте изменения с `servers.yml` и документацией по добавлению нод ([07-add-ru-relay.md](07-add-ru-relay.md), [08-add-foreign-exit.md](08-add-foreign-exit.md)).
