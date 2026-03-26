#!/bin/bash

# Настройки
PREFIX="51.250."               # нужный префикс
ZONES=("ru-central1-a" "ru-central1-b") # Указать зоны, но не больше чем квота по IP-адресам (по умолчанию 2, можно запросить больше)
MAX_ATTEMPTS=2000                # максимальное количество циклов
ATTEMPT=0
SLEEP_BETWEEN_CYCLES=2         # пауза между циклами (сек)

# Функция для создания адреса в указанной зоне
create_address() {
  local zone=$1
  yc vpc address create \
    --name "temp-addr-$zone" \
    --external-ipv4 zone="$zone" \
    --format json 2>/dev/null
}

# Функция для получения IP адреса по имени
get_address_ip() {
  local name=$1
  yc vpc address get "$name" --format json 2>/dev/null | jq -r '.external_ipv4_address.address'
}

# Функция для удаления адреса по имени
delete_address() {
  local name=$1
  yc vpc address delete "$name" >/dev/null 2>&1
}

# Основной цикл
while (( ATTEMPT < MAX_ATTEMPTS )); do
  (( ATTEMPT++ ))
  echo "=== Attempt $ATTEMPT ==="

  # Создаём адреса во всех зонах параллельно
  echo "Creating addresses in zones: ${ZONES[*]}"
  pids=()
  for zone in "${ZONES[@]}"; do
    create_address "$zone" &
    pids+=($!)
  done

  # Ждём завершения всех созданий
  for pid in "${pids[@]}"; do
    wait "$pid"
  done

  # Проверяем IP полученных адресов
  found=0
  found_zone=""
  found_ip=""
  for zone in "${ZONES[@]}"; do
    name="temp-addr-$zone"
    ip=$(get_address_ip "$name")
    if [[ -z "$ip" ]]; then
      echo "  ⚠️  Failed to get IP for $name"
      continue
    fi
    echo "  Zone $zone → $ip"
    if [[ $ip == $PREFIX* ]]; then
      found=1
      found_zone="$zone"
      found_ip="$ip"
      echo "  ✅ Match found in $zone!"
      break
    fi
  done

  # Если нашли подходящий адрес
  if (( found )); then
    # Удаляем остальные адреса
    for zone in "${ZONES[@]}"; do
      if [[ "$zone" != "$found_zone" ]]; then
        delete_address "temp-addr-$zone"
        echo "  🗑️  Deleted temp-addr-$zone"
      fi
    done
    # Переименовываем найденный адрес, чтобы не потерять
    new_name="static-ip-${found_ip//./-}"
    yc vpc address update "temp-addr-$found_zone" --new-name "$new_name" >/dev/null
    echo "🎉 Done! Reserved IP: $found_ip (name: $new_name, zone: $found_zone)"
    exit 0
  fi

  # Если не нашли — удаляем все созданные адреса
  echo "  ❌ No matching IP in this attempt."
  for zone in "${ZONES[@]}"; do
    delete_address "temp-addr-$zone"
  done
  echo "  Sleeping ${SLEEP_BETWEEN_CYCLES}s before next attempt..."
  sleep "$SLEEP_BETWEEN_CYCLES"
done

echo "❌ Failed to find IP with prefix $PREFIX after $MAX_ATTEMPTS attempts."
exit 1
