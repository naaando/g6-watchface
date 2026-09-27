# Captura passiva de watchface via BLE (G6 / Trek 1)

Captura o BIN que o AuraFit envia do Galaxy A54 para o relógio, pelo log HCI do
Android. Nada é transmitido: o script só lê um log de captura.

## Por que este caminho

O `WatchManager` do JieLi não expõe operações de watchface no G6
(`g6-cat-gauge-transfer/KNOWLEDGE.md`), mas o fluxo do AuraFit
(`com.szabh.smable3`, `WatchFaceBuilder`) funciona. Interceptar esse fluxo dá:

- o BIN exato de qualquer watchface que o AuraFit sabe enviar;
- o protocolo real em operação (MTU, opcode ATT, tamanho de chunk, handshakes).

## Passos

1. No A54: **Opções do desenvolvedor → Ativar registro HCI do Bluetooth**.
   Confirme com `adb shell settings get global bluetooth_btsnoop_log_mode` (2 = ativo).
2. Conecte o G6 no AuraFit normally e **baixe o watchface novo**. Espere a
   confirmação na tela do relógio.
3. Imediatamente após, sem fazer mais nada no celular:

   ```bash
   ./pull_snoop.sh ../ble-capture/run-2026-09-27
   python3 parse_btsnoop.py ../ble-capture/run-2026-09-27/btsnoop_hci.log -o ../ble-capture/run-2026-09-27/captured
   ```

4. Se `dial(s) extracted` for 0, rode com `--dump-streams` e inspecione os
   `.stream` para ver o que passou (ver *Plano B*).

## Como funciona

`parse_btsnoop.py`:

1. lê o container btsnoop (aceita o `.log` direto ou o bugreport zip);
2. classifica pacotes HCI (com ou sem byte de tipo) e mapeia
   `handle → endereço` pelos eventos *LE Connection Complete*;
3. remonta L2CAP por conexão e direção, e extrai o payload de
   ATT Write (0x52/0x42) e Handle Value Notification (0x1B/0x1D);
4. separa sessões por ociosidade (`--gap`, padrão 3 s);
5. desembrulha o framing `0xAB` do JieLi (abaixo) e valida a integridade pelos
   offsets;
6. procura o container HK89 do dial no resultado: `u16 pltable_size`,
   `u8 num_blocks`, `u8 format`, `num_blocks × 20` bytes de descritores,
   `pltable_size × u32` de tamanhos, e os dados. O comprimento exato sai da
   própria tabela, então o BIN é cortado no tamanho certo, sem cauda de
   protocolo.

Formato do container: `Fogg/comp_decomp.py:1195-1350`.

## O framing `0xAB` do JieLi (SMA)

O BIN **não** trafega cru. Cada escrita ATT carrega exatamente um frame
proprietário do JieLi:

```
ab | type | len_hi len_lo (big endian) | ?? | ?? | body...
0     1       2             3           4    5    6 .. 6+len
```

- `type` `0x01` = frame de dados, `0x11` = acknowledgement;
- o corpo de um frame de dados tem um **prólogo de 12 bytes** seguido dos bytes
  do arquivo (1018 bytes por frame, 1030 no total);
- os 2 últimos bytes do prólogo são o offset acumulado no arquivo como contador
  de **16 bits que dá a volta** (rola em 65536). O campo mais serve como
  verificação de integridade do que de endereçamento.

Numa captura real (618.808 bytes, 32,4 s) vieram 608 frames de dados + 608 acks,
offsets contíguos, 607 × 1018 + 882 = 618.808 bytes — exatamente o tamanho
previsto pelo header HK89.

## Armadilhas já encontradas

Cada uma destas corrompeu a captura real antes de ser corrigida:

- **Bit de direção do ACL HCI é o bit 15**, não o bit 0. Usar o bit 0 faz o
  handle `0x0040` virar `0x0041` e classifica tudo como TX.
- **A semântica do flag PB depende do tipo de link** (Core spec 4.2.1):
  em LE, `0b01` é *continuação*; em BR/EDR, `0b10` é continuação. Usar a tabela
  errada dessincroniza o L2CAP inteiro — o handle `0x0004` tinha 661.954 bytes
  de ACL e só 28.954 viravam CID `0x0004`; o resto virava CIDs absurdos
  (`0xFFFF`, `0x8E20`…).
- **`pltable_size` é uma contagem de entradas `u32`, não um tamanho em bytes.**
  O palpite antigo de exigir múltiplo de 4 funcionava por acaso (os dois BINs
  originais davam 64 e 32) e rejeitou o dial capturado, que dá 126.
- **Um header HK89 que "casa" não basta.** Sem exigir que o container termine
  exatamente no fim do buffer, o stream cru de frames `0xAB` produz um falso
  positivo. Use `--allow-trailing` só se precisar.
- Header ATT de escrita é `opcode + handle`, sem campo extra; evento HCI
  satisfaz `body[1] + 2 == len(body)`, comando satisfaz `body[2] + 3 == len(body)`.

## Validação do parser

`selftest.sh` sintetiza um btsnoop que carrega um BIN real em escritas ATT de
177 bytes e compara o sha256. Roda 8 casos: os dois originais do G6 e o dial
capturado, cada um por `le:att`, `bredr:rfcomm`, e os dois sem evento de
conexão (forçando o sniffing de transporte).

```bash
./selftest.sh
```

`make_fake_snoop.py` é o gerador; aceita `--transport att|rfcomm`, `--link
le|bredr` e `--no-complete` para cobrir os quatro caminhos.

## Segurança

- Captura é passiva. Nenhum comando BLE é enviado, nenhum arquivo é gravado no G6.
- Nunca use OTA, firmware update, resource update ou restore no G6
  (`g6-cat-gauge-transfer/TRANSFER_STEPS.md`).
- Registre o SHA-256 de cada BIN capturado em `SHA256SUMS.txt`.
