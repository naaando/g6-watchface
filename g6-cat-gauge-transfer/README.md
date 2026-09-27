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

### 1. Editar a prévia (opcional)

O sistema de prévia fica em `preview/`, na raiz do repositório — não é específico deste pacote.

```bash
# A partir da raiz do projeto
open preview/index.html     # abre qualquer .bin, decodifica no navegador
open preview/authoring.html # troca a arte contra uma geometria fixa, antes de compilar
```

`authoring.html` usa `config.js` (posições, dimensões e rotações) e os assets em `preview/assets/`. Para modificar o visual, edite os PNGs em `preview/assets/` e ajuste `config.js` conforme necessário.

`index.html` é o caminho rápido para conferir o resultado: escolha o `.bin` e ele é lido direto no navegador, sem etapa de conversão.

### 2. Validar assets da prévia

Antes de compilar, verifique se todos os assets estão corretos e consistentes com o `dial_desc.json`:

```bash
python3 preview/validate-preview-assets.py
```

Saída esperada: `preview assets: PASS`

O script verifica:
- Todos os arquivos referenciados em `config.js` existem em `preview/assets/`
- O canvas é 466×466
- Os nomes dos blocos correspondem ao `dial_desc.json`
- Todos os blocos do `dial_desc.json` (exceto `BLK_PREV`) têm uma camada correspondente em `config.js`

### 3. Exportar assets para compilação

Copie os PNGs de `preview/assets/` para `assets/` (o diretório usado pelo compilador):

```bash
cp ../preview/assets/*.png assets/
```

### 4. Compilar o BIN

Use o script de compilação em `source/` para gerar o BIN a partir de `assets/dial_desc.json`:

```bash
cd source
python3 compile.py  # ou o script de compilação disponível
```

### 5. Verificar os 8 blocos

Após a compilação, valide se os 8 blocos do BIN correspondem ao `dial_desc.json`:

```bash
python3 source/validate-bin.py  # se disponível
```

### 6. Construir o APK

```bash
cd sender
./gradlew assembleDebug -PbuildPython=/opt/homebrew/bin/python3.12
```

### 7. Instalar e testar

```bash
adb install -r sender/app/build/outputs/apk/debug/app-debug.apk
```

## Procedimento seguro de transferência

1. Mantenha o G6 carregado e próximo do Galaxy A54.
2. Feche ou desconecte o AuraFit antes de testar outro remetente BLE; dois aplicativos podem disputar a conexão.
3. Abra o APK e use somente scan, conexão, informações do dispositivo e envio do dial.
4. Não use OTA, atualização de firmware, `Update Resource`, restauração ou funções equivalentes.
5. Se o envio falhar, feche o remetente, abra o AuraFit e reconecte o relógio por ele.

O BIN ainda não foi enviado ao G6 nesta sessão. A prévia e a validação binária passaram; a transferência real continua sendo o próximo teste controlado.

## Integridade

Veja `SHA256SUMS.txt`. O APK foi compilado com:

```text
./gradlew assembleDebug -PbuildPython=/opt/homebrew/bin/python3.12
```
