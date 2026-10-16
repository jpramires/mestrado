# COMISET - cenário lab: campos disponíveis ao longo dos `_source`s

## Estrutura

{
    "_index": "logs-endpoint-winevent-additional-2022.11.16",
    "_type": "_doc",
    "_id": "8c0acd213cc3524fc717afbc33644d9c2eb6626c",
    "_score": 1,
    "_source": {<JSON fortemente aninhado>}
}

## Resumo Executivo

- Total de eventos:    49,914,325
- Eventos maliciosos: ~1,713,709 (3.4%) - identificados via `rule_technique_id`
- Campos únicos:       1,293
- Formato original:    NDJSON dentro de ZIP → convertido para Parquet+ZSTD (159 GB → 3.3 GB)
- Schema: heterogêneo - cada EventID do Windows traz campos diferentes; campos ausentes ficam como `null`
- Origem: Winlogbeat 8.5 → Logstash/Kafka → Elasticsearch (stack ELK)

---

## Labels MITRE ATT&CK

Campos centrais para análises de segurança no dataset:

| campo                 | n_eventos  | descrição                                                         |
|-----------------------|------------|-------------------------------------------------------------------|
| `RuleName`            | 49,470,758 | nome da regra Sysmon que gerou o evento; pode conter tática MITRE |
| `rule_technique_name` | 1,714,728  | nome da técnica MITRE (ex: "Command and Scripting Interpreter")   |
| `rule_technique_id`   | 1,713,709  | ID da técnica MITRE (ex: T1059)                                   |
| `rule_technique`      | 134        | campo legado/alternativo; poucos eventos                          |
| `tags`                | 2,232      | tags livres do Logstash; podem conter classificações adicionais   |

---

## Campos universais (presentes em todos os ~49.9M eventos)

Estes campos existem em 100% dos eventos - seriam o 'esqueleto' do dataset:

| campo                          | descrição                                                       |
|--------------------------------|-----------------------------------------------------------------|
| `@timestamp`                     | timestamp principal do evento (ISO 8601) (2026-04-08T15:30:00Z) |
| `event_original_time`            | timestamp original do Windows antes do ETL                      |
| `event_id`                       | ID do tipo de evento Windows (ex: 4688, 4624, 5858)             |
| `host_name`                      | hostname da máquina que gerou o evento                          |
| `log_name`                       | canal de log Windows (ex: Security, Sysmon/Operational)         |
| `level`                          | severidade (information, error, warning)                        |
| `source_name`                    | provedor do evento (ex: Microsoft-Windows-Sysmon)               |
| `type`                           | tipo de coletor (wineventlog)                                   |
| `record_number`                  | número sequencial do evento no canal                            |
| `z_elastic_ecs`                  | subestrutura ECS - campos reembalados no padrão Elastic         |
| `@version`                       | versão interna do Logstash                                      |
| `beat_version`                   | versão do Winlogbeat                                            |
| `etl_host_agent_type`            | tipo de agente ETL                                              |
| `etl_host_agent_uid`             | ID único do agente (persistente)                                |
| `etl_host_agent_ephemeral_uid`   | ID efêmero do agente (muda por restart)                         |
| `etl_pipeline`                   | lista de passos de transformação aplicados ao evento            |

---

## Grupos de campos por categoria

### Identidade e autenticação (~39.5M eventos)

| campo                                    | n_eventos   |
|------------------------------------------|-------------|
| `user_name`                              | 39,522,572  |
| `user_domain`                            | 39,522,572  |
| `user_account`                           | 39,474,823  |
| `meta_user_name_is_machine`              | 39,522,572  |
| `user_sid`                               | 43,093      |
| `user_logon_id`                          | 43,093      |
| `LogonId`                                | 36,917      |
| `LogonGuid`                              | 44,103      |
| `logon_type`                             | 16,880      |
| `AuthenticationPackageName`              | 5,923       |
| `SubjectUserName` / `SubjectDomainName`  | ~24,000     |
| `TargetUserName` / `TargetDomainName`    | ~16,000     |
| `ElevatedToken`, `ImpersonationLevel`    | ~6,000      |

### Processos (no sentido de SO)

| campo                     | n_eventos   |
|---------------------------|-------------|
| `process_name`            | 49,494,944  |
| `process_path`            | 49,494,944  |
| `process_id`              | 49,891,223  |
| `process_guid`            | 49,445,112  |
| `thread_id`               | 49,891,223  |
| `process_parent_name`     | 38,027      |
| `process_parent_path`     | 38,027      |
| `process_parent_guid`     | 36,769      |
| `process_parent_id`       | 36,769      |
| `target_process_name`     | 9,970,343   |
| `target_process_path`     | 9,970,343   |
| `target_process_id`       | 9,970,343   |
| `target_process_guid`     | 9,970,284   |
| `CommandLine`             | 36,771      |
| `ParentCommandLine`       | 36,769      |
| `CurrentDirectory`        | 36,769      |
| `IntegrityLevel`          | 36,769      |
| `ProcessCreationTime`     | 3,592       |
| `CallTrace`               | 9,963,862   |
| `GrantedAccess`           | 9,963,862   |

### Rede

| campo                             | n_eventos             |
|-----------------------------------|------------------------|
| `src_ip_addr`                     | 1,199,531              |
| `dst_ip_addr`                     | 1,197,990              |
| `DestinationPort`                 | 1,197,989              |
| `SourcePort`                      | 1,197,989              |
| `Protocol`                        | 1,207,770              |
| `DestinationHostname`             | 1,197,989              |
| `SourceHostname`                  | 1,197,989              |
| `Initiated`                       | 1,197,989              |
| `src_ip_public` / `dst_ip_public` | 1,199,531 / 1,197,990  |
| `QueryName` / `QueryResults`      | 18,406 / 17,466        |
| `PipeName`                        | 414,628                |

### Arquivos

| campo                          | n_eventos   |
|--------------------------------|-------------|
| `TargetFilename`               | 1,747,743   |
| `file_creation_time`           | 1,649,906   |
| `file_previous_creation_time`  | 46,409      |
| `TargetObject`                 | 36,027,534  |

### Hashes e assinaturas

| campo             | n_eventos  |
|-------------------|------------|
| `hash_md5`        | 175,826    |
| `hash_sha1`       | 175,826    |
| `hash_sha256`     | 175,826    |
| `hash_imphash`    | 175,826    |
| `Signature`       | 41,222     |
| `SignatureStatus` | 41,220     |
| `Signed`          | 41,220     |
| `ImageLoaded`     | 41,220     |

### Registro Windows

| campo                         | n_eventos   |
|-------------------------------|-------------|
| `TargetObject`                | 36,027,534  |
| `EventType`                   | 36,442,162  |
| `Details`                     | 1,195,642   |
| `object_name` / `object_type` | ~41,000     |

### Acesso a processos (técnicas de injection)

| campo            | n_eventos   |
|------------------|-------------|
| `SourceUser`     | 9,970,284   |
| `TargetUser`     | 9,970,284   |
| `CallTrace`      | 9,963,862   |
| `GrantedAccess`  | 9,963,862   |
| `SourceThreadId` | 9,963,862   |

### Tarefas agendadas

| campo            | n_eventos  |
|------------------|------------|
| `TaskName`       | 61,577     |
| `TaskInstanceId` | 16,974     |
| `TaskEngineName` | 465        |

### Scripts e execução

| campo             | n_eventos  |
|-------------------|------------|
| `ScriptBlockText` | 1,579      |
| `ScriptBlockId`   | 1,579      |

### ETL e infraestrutura (provávelmente ruído)

Campos que descrevem o pipeline de coleta, não o evento em si:

- `@version`
- `etl_pipeline`
- `etl_version`
- `etl_processed_time`
- `etl_kafka_topic`
- `etl_kafka_offset`
- `beat_version`
- `beat_hostname`
- `beat_name`
- `etl_host_agent_ephemeral_uid`

### Hardware e sistema (baixo valor analítico)

Eventos de disco, NTFS, power management, drivers:

- `BucketIo*`
- `MftBitmap*`
- `RootIndex*`
- `UserDisk*`
- `BugcheckParameter*`
- `SleepInProgress`
- `PowerButtonTimestamp`
- `MinimumThrottlePercent`
- `DeviceQueue*`
- `TotalDevice*`

---

## Campos raros (< 10 eventos) - provável garbage ou one-off

- `user_reporter_*`                  (1 evento cada)
- `action`                           (1)
- `number`                           (1)
- `network_initiated`                (1)
- `fingerprint_network_community_id` (1)
- `AbortSupported`                   (4)
- `PublisherGuid`                    (5)

---

## Para process mining — colunas mínimas necessárias

```
case_id    →  process_guid       (ou host_name + session)
activity   →  rule_technique_id  (ataques) ou event_id (todos)
timestamp  →  @timestamp
```

Campos de enriquecimento recomendados:

- `rule_technique_name`
- `host_name`
- `user_name`
- `process_name`
- `process_parent_name`
- `CommandLine`
