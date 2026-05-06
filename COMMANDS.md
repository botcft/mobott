# Bot commands

| Command | Description |
|---------|-------------|
| `/new <CODE> <Company Name>` | Create a new Telegram group: name it by code + company, add members, promote admins, send welcome, then reply in this chat with invite link and QR. Example: `/new TMTP Acme` |
| `/addcode` | Multi-step wizard: anyone can define a new CODE; it is saved to `config/dynamic_codes.yaml` on the machine running the bot. Built-in codes in `codes.yaml` cannot be replaced. Use `/cancel` to abort. |

**Codes** (see `config/codes.yaml` and `config/dynamic_codes.yaml`): TEST, TMTP, TMTE, FDF, FE, NBSC, NBSDF, CRUSHC, plus any added via `/addcode`.
