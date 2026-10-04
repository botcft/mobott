# Bot commands

| Command | Description |
|---------|-------------|
| `/new <CODE> <Company Name>` | Create a new Telegram group: name it by code + company, add members, promote admins, send welcome, then reply in this chat with invite link and QR. Example: `/new TMTP Acme` |
| `/addcode` | Multi-step wizard: anyone can define a new CODE; it is saved to `config/dynamic_codes.yaml` on the machine running the bot. Built-in codes in `codes.yaml` cannot be replaced. Use `/cancel` to abort. |
| `/deletecode` | Remove a code from `dynamic_codes.yaml` (bot-added only). `/deletecode` lists deletable codes; `/deletecode CODE` asks for confirmation. Built-in `codes.yaml` entries cannot be deleted here. |
| `/cancel` | Cancel the `/addcode` wizard. |
| `/skip` | During `/addcode`, skip the welcome message step. |
| `/start` | Show welcome text and command list. |

**Codes** (see `config/codes.yaml` and `config/dynamic_codes.yaml`): TEST, TMTP, TMTE, FDF, FE, NBSC, NBSDF, CRUSHC, plus any added via `/addcode`.
