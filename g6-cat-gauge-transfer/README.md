# G6 / Trek 1 — pacote de transferência

Este pacote contém o watchface de teste inspirado no medidor do Need for Speed 2 e o APK do remetente JieLi/SMA preparado para o Galaxy A54.

## Arquivos principais

- `cat-gauge-analog-test.bin`: watchface compilado, usando o layout oficial do G6 `0.0_AM05_G6_11448.bin`.
- `cat-gauge-analog-test.apk`: APK debug instalado no A54; inclui o BIN em `assets/dials/`.
- `preview-with-official-hands.png`: prévia analógica com os ponteiros oficiais recoloridos.
- `preview-digital-concept.png`: conceito visual com hora digital; os dígitos ainda não estão no BIN analógico.
- `assets/`: fundo, ponteiros, sprites e descrição do dial.
- `source/`: script e descrição usados na compilação.
- `sender/`: projeto-fonte do APK, sem `build/` e sem caminhos locais do SDK.
- `KNOWLEDGE.md`: conhecimento técnico consolidado e limites conhecidos.

## Workflow completo: edição → compilação → verificação → APK

### 1. Editar e conferir no editor

O editor fica em `Fogg/dial-designer/`, um clone de terceiros — não é específico deste pacote:

```bash
# A partir da raiz do projeto
cd Fogg/dial-designer
npm install
npm run dev
```

Clique em **Decompile Existing Dial** e escolha `dials/cat-gauge-analog-test.bin`
(ou qualquer outro `.bin` de `dials/`). Ele decompila em camadas selecionáveis
e recompila para `.bin` com **Compile & Download .bin**.

Para trocar só a arte antes de compilar, edite os PNGs em `assets/` deste
pacote — as posições e dimensões vêm de `assets/dial_desc.json`, e é ele que o
compilador lê.

Atenção: o editor é um **visualizador**. As complicações vêm de valores mock,
e alguns estão errados de um jeito que importa (o mês fica fixado em maio, o
contador de passos perde o dígito da frente, o anel de pulso segue o slider de
bateria). A lista completa, com arquivo e linha, está em
[`docs/fogg-dial-format-and-renderer-bugs.md`](../docs/fogg-dial-format-and-renderer-bugs.md).

### 2. Validar assets

O `dial_desc.json` é a fonte da geometria. Confira antes de compilar:

```bash
python3 -c "import json;d=json.load(open('assets/dial_desc.json'));print(len(d['blocks']),'blocos');[print(f\"  {b['type']:<16} {b['width']}x{b['height']} frms={b['frms']} @ {b['posx']},{b['posy']}\") for b in d['blocks']]"
```

Todos os blocos, menos `BLK_PREV`, devem ter um PNG correspondente em `assets/`
com o mesmo nome de arquivo (`fname`).

### 3. Compilar o BIN

Use o script de compilação em `source/` para gerar o BIN a partir de `assets/dial_desc.json`:

```bash
cd source
python3 compile.py  # ou o script de compilação disponível
```

### 4. Verificar os 8 blocos

Após a compilação, valide se os 8 blocos do BIN correspondem ao `dial_desc.json`:

```bash
python3 source/validate-bin.py  # se disponível
```

### 5. Construir o APK

```bash
cd sender
./gradlew assembleDebug -PbuildPython=/opt/homebrew/bin/python3.12
```

### 6. Instalar e testar

```bash
adb install -r sender/app/build/outputs/apk/debug/app-debug.apk
```

## Procedimento seguro de transferência

1. Mantenha o G6 carregado e próximo do Galaxy A54.
2. Feche ou desconecte o AuraFit antes de testar outro remetente BLE; dois aplicativos podem disputar a conexão.
3. Abra o APK e use somente scan, conexão, informações do dispositivo e envio do dial.
4. Não use OTA, atualização de firmware, `Update Resource`, restauração ou funções equivalentes.
5. Se o envio falhar, feche o remetente, abra o AuraFit e reconecte o relógio por ele.

O BIN ainda não foi enviado ao G6 nesta sessão. A decodificação e a validação binária passaram; a transferência real continua sendo o próximo teste controlado.

## Integridade

Veja `SHA256SUMS.txt`. O APK foi compilado com:

```text
./gradlew assembleDebug -PbuildPython=/opt/homebrew/bin/python3.12
```
