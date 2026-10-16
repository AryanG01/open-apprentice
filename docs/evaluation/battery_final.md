# Final battery freeze (Plan 5)

Frozen 2026-10-16 with `oa eval freeze --split final` before any learner run. The private files live in
`benchmarks/final/battery/` (git-ignored); only their hashes and the learner-projected manifest are committed here.
`oa eval run --split final` re-hashes every file against `battery_final.hashes.json` and refuses on any mismatch.
Earlier freezes were replaced before any learner ran on the final split: v2.1 (its scope-diagnostic set could not
tell a near-miss selector apart) and the first v2.2 freeze (public seed base; learner files carried unmasked
correction outputs; both found by the final review). No learner ever read a final episode.

- Generator: `battery-v2.3`, scoring `score-v2.1`, tolerance 1/2
- Generator code commit: `127f116ebf64a201c9ba83dc2db947c5ff048528`
- Seed base: drawn at freeze time and recorded only in the private manifest (development: 110000)
- `manifest.private.json` sha256: `b1f6eacbf1559c655a77623315c52948fded99df1e8f6a0667e9a40dfd346134`
- `manifest.public.json` sha256: `d35a6b7e9089ca2ebbbd6e2d5b49433a30d1953575b442a4658917c0b565d976`
- Episodes: 36 (catalogue 8, beyond 8, inconsistent 4, unsupported 4, sequential 12) plus 3 real-file episodes on
  `benchmarks/final/drawio/f1-f3` (bytes hashed and matched to `docs/corpus/drawio_provenance.md`; contents not parsed).

## Public manifest (opaque ids)

```json
{
 "episodes": [
  "e0589ff7692",
  "e0ef68b5765",
  "e0f21bde332",
  "e167f4be004",
  "e1beb848fe8",
  "e225b49e9a3",
  "e247783934f",
  "e2834f747ae",
  "e371fe329f9",
  "e37d57569f9",
  "e46e9a2c35e",
  "e4cf599184d",
  "e515b65577a",
  "e53f49247ce",
  "e5ccdc91408",
  "e608bf9464e",
  "e6248b2b29d",
  "e6a9773be91",
  "e6c86a5ebc2",
  "e8550264e92",
  "e88fa81edd7",
  "e9b9637da0f",
  "ea0fc3aba12",
  "ea2179b1ea6",
  "ea35e08d122",
  "ea55d264111",
  "ea87070f33d",
  "eac04c7e6db",
  "eb6e0a33c09",
  "ec4b3681577",
  "ec949a58b5a",
  "ed8e392e213",
  "ee799a5cb57",
  "ef6906243da",
  "efd8d946fc4",
  "effc94c7633"
 ],
 "split": "final"
}
```

## File hashes

| file | sha256 |
|---|---|
| `episodes/e0589ff7692.private.json` | `350701a2070b0ff2f64d94f8b076dc8a7b83c66436e147952e4a905811408f50` |
| `episodes/e0ef68b5765.private.json` | `34a47c4dd5eb1f7ec356a54e050e62cf227530c23f60f4a37da0758e74d84b43` |
| `episodes/e0f21bde332.private.json` | `732de7dd0f43a577c038f39c2772b8fda74d7a8ad6f482f43deffe9be6414a3e` |
| `episodes/e167f4be004.private.json` | `eb6b76bd7599b5ec21d6a4eeb2003cf9d22927c94eeb2b5b585ea759114a3d29` |
| `episodes/e1beb848fe8.private.json` | `e21f155f00d4f96fc64cd400d499c92f5e33e25358311f8faffb17bf47d8285a` |
| `episodes/e225b49e9a3.private.json` | `0f9465c2466a53a308c50ef072f829c6d38b55084cb6feb688bfb450cb3ffc60` |
| `episodes/e247783934f.private.json` | `da205064ce5e0d4888ab8dbab857299d837d4f0ef2c478f9ae1f556ea8ca48f1` |
| `episodes/e2834f747ae.private.json` | `f4ff88dddd756bdcacb0d36025b6dd4398300dbb5cfc544132405220df6f23c5` |
| `episodes/e371fe329f9.private.json` | `093628790a06aa0cab9f4709bda0c4021710f0801b46f2a2c093cbf0a88914d5` |
| `episodes/e37d57569f9.private.json` | `1640b7a8002a8b16f52bf714686d7bf0a3248789639905c06521005a3b510bad` |
| `episodes/e46e9a2c35e.private.json` | `6d0531ba25e2cf2b2956764fbe5cd4978eec31076c17ed0fbd53957fbfbd90d0` |
| `episodes/e4cf599184d.private.json` | `cf3640a94411274c5f28741ceb18b8f0387f47015096ad2958b471c1628841a0` |
| `episodes/e515b65577a.private.json` | `e189124e8e1b832313f524ed5f68532b6a8400e1cc78efeea758ec6bda08bd44` |
| `episodes/e53f49247ce.private.json` | `d261dc5683538b88bb56ac10a6bcb01c3e560cd0f2d61d1c8dfcdaa7fa90be1f` |
| `episodes/e5ccdc91408.private.json` | `b3225ad2a7c05eeedc92eec748e32cec6de8dec2d82e0a415d812d1c7ec4c991` |
| `episodes/e608bf9464e.private.json` | `244bdff63416cbe957442eb5cd3870eda3fbe0f3a842c8e5906f903563c35bb2` |
| `episodes/e6248b2b29d.private.json` | `25ad3b9072c7aa35fa1ad55be5908df7aa0093ad44b4946f2f9545b5b1a9f755` |
| `episodes/e6a9773be91.private.json` | `f1a0fbd4d94e2407ee132b5c41e921269833f117c2f8c68ef3afe51f98bf65f3` |
| `episodes/e6c86a5ebc2.private.json` | `b0237b5c751ada90c7d153ec72a95b0afc0643eb2db12dfbaec314e9cbd0ac16` |
| `episodes/e8550264e92.private.json` | `2efd88013c9a15b66db258877504079b7f2d6ffec910476caea8a02bddeda46d` |
| `episodes/e88fa81edd7.private.json` | `e3a2a4a6c7cd486d1f749efcb86564b99bf51ee300799c0299f92b7b2f7608e6` |
| `episodes/e9b9637da0f.private.json` | `676aaa02c4355e312528597b94912eb11d21de793b1aef31c87a9b9d4c6bed3d` |
| `episodes/ea0fc3aba12.private.json` | `fcb5d58c62d2954ed22f17e347c2611d222cf00cf7d8de579350d824543a4d1f` |
| `episodes/ea2179b1ea6.private.json` | `52d6550122e82ee4382cdd2d12af933cda3ed707b84363497ef9cce472a6db87` |
| `episodes/ea35e08d122.private.json` | `5b97ea2ad487266425649a0e369760ea5f36f433e0100af3e9482d572d78d344` |
| `episodes/ea55d264111.private.json` | `5a4176720b28edec467cf770c0a6dcaeb7f7121ba630f41bb1556dae2b13356d` |
| `episodes/ea87070f33d.private.json` | `dcad1feb41801a0fa4710cdee06ae09651e3505fb4c1d2ce816218256b1f0e69` |
| `episodes/eac04c7e6db.private.json` | `bf4eddac1953aa0ebf749197f6e5c882a68b98fd72aa2ade26a92298624b29de` |
| `episodes/eb6e0a33c09.private.json` | `b5302d3fc0eed9314875ea4a38fcfd0feb119e1c6d412e97b3f2a4d6479f8290` |
| `episodes/ec4b3681577.private.json` | `0a5c19320e0391ce56015dfe168e73e2a862d52d2fab697c5a8ebee1861bf475` |
| `episodes/ec949a58b5a.private.json` | `3dc670c8fdb030e3c06115b437de4c393cbc4f8e239d885f6dec7bbabefd2bff` |
| `episodes/ed8e392e213.private.json` | `aee9fd2d131734ee3804cc72504e8632ce591379abfcf875530e93e8e4f8d406` |
| `episodes/ee799a5cb57.private.json` | `5cefb32f87aefc3310f1958ac313b3a48d14de731228a696978571fcfae550c6` |
| `episodes/ef6906243da.private.json` | `9c5435a6f4f1cd815d500d373f1095eec0812953711be6708eb426b341f72c24` |
| `episodes/efd8d946fc4.private.json` | `11d14ee45bc3ffaea03f0bd4900ba1a741fcc12aad6f56d207382569652b73dc` |
| `episodes/effc94c7633.private.json` | `66cf7dd0812c7468bd6c6a3a0b4fe2eee7f6e1fe50904d5acd24723227664909` |
| `learner/e0589ff7692.json` | `e2f446c9f6e890aa60a64f54a68ecea48e55fc485f026088a94784aa210d7c28` |
| `learner/e0ef68b5765.json` | `582e8439fdc4491ce9ca28a20fddde07c6442dc06bd7669980d478939cfe7840` |
| `learner/e0f21bde332.json` | `f0f6688ab69a6fa53c82abcf03f7763b6c743c95a0e93d133229893507dd1c44` |
| `learner/e167f4be004.json` | `954e40afc5ba11abbf6bf67cf246dc00e8bf78d10013cdc3273dfdb9453e0d15` |
| `learner/e1beb848fe8.json` | `db84f4e19603843c33d52892452ff585a2ad5adbd8f52e1db1abc8a40e0b7e57` |
| `learner/e225b49e9a3.json` | `21afd468d96760dcb633ad14bec78ddac908d115a63db5dd6ed5116129855bf4` |
| `learner/e247783934f.json` | `5d28f5ae2de478093e19a5a9e7793c8df0fa2838a745c7f44259b0899b33c6ad` |
| `learner/e2834f747ae.json` | `55ae42143a7893a01e602cc3e9ebd8c690eea0698edc0e0d0c7a8aa35a17b1e7` |
| `learner/e371fe329f9.json` | `9ae1e5201ac4e90b2806184c0c26dfa8941848a9ac9e88c46f64e370e216d52a` |
| `learner/e37d57569f9.json` | `b932ab084e379fbe993d7b333db0480c6288d3bb4919b35e440bd4837c3a2ef4` |
| `learner/e46e9a2c35e.json` | `785b777c336fe95f4bb6d63eb1c72c1b74a0e27fdb96911b4d00551ae0983dab` |
| `learner/e4cf599184d.json` | `0bc3bb72fd2c12790d0db50d477b0ab168d2d9c7393c51f997335be6d00851f0` |
| `learner/e515b65577a.json` | `7b11c904a7eeb044252e5d3a04c872dc7882727f1e788acae6419975b280ff27` |
| `learner/e53f49247ce.json` | `609d4c48a137b4a930cc407067e7a53fe92c49ae0a9496e2f27f91cd963d6f34` |
| `learner/e5ccdc91408.json` | `7b5f7ab76103d66b26b8435b2967234815c99e500792f86db6977b6b2f13a41c` |
| `learner/e608bf9464e.json` | `62120d7a7b1795d37061ee779b60e8a2e0a574346493a37467e577f53693309e` |
| `learner/e6248b2b29d.json` | `c99bd414cff41bd8f00cbe510a1e2fe1b5d188f73402ea0a76452be35009a142` |
| `learner/e6a9773be91.json` | `1d87a0476d658a7cd579fc8c1b2da2bbd1b71f548b44c4abcea01048c8d806fd` |
| `learner/e6c86a5ebc2.json` | `31bafe405a6fdf2bd0ce21ea16772fba5692adc5d631dc3b9f223d1d0a02810c` |
| `learner/e8550264e92.json` | `095e8ab9e899fe3c0ab5b7586fd6c8cd723883c0c1dc7ce8a0f2f3b6dc9a7784` |
| `learner/e88fa81edd7.json` | `38ff90922832cb341f6f0d261f77567bf521109db61a8019e5c0b15d1b3b0cd8` |
| `learner/e9b9637da0f.json` | `57bf353265cf5b2edd6d43690ead575ad59818afe244314d011bab4caeb7f680` |
| `learner/ea0fc3aba12.json` | `d9817bf41cc5a7e2f210fbf9ac56e8549eecd785347748856d4592d317c3de42` |
| `learner/ea2179b1ea6.json` | `74330c770cc017abf402cfaf52b9363dc5186d88613ddffc85aef752b214ff4d` |
| `learner/ea35e08d122.json` | `f2e69b183b55869e2cad975a484960dca6e6942f683ff74f4d32e664db4e1492` |
| `learner/ea55d264111.json` | `0b8dc77fe9ee356327cddfa6f447213841a129e97777350f2c735549aa453bbe` |
| `learner/ea87070f33d.json` | `e2c70d6c8214369130436348d692f9befd780706c33bb70534ef257f368bcb45` |
| `learner/eac04c7e6db.json` | `e4770adafc57851d8f97755c4037a4bffabd6400eff466e010ada0864204d5a3` |
| `learner/eb6e0a33c09.json` | `5e6ee8cdf917b0f39eae58c8678598bdab7ef81982e27c3827fdb31ea2316d51` |
| `learner/ec4b3681577.json` | `dbc8df9ee0d863ad4c2f46f31548eb313ac2a3d6ddf13c513d434a01e50077aa` |
| `learner/ec949a58b5a.json` | `9600e979567b62f3da2981219e16c9c99bdb7fe7176e921ea5ff68fc1a947b95` |
| `learner/ed8e392e213.json` | `cb206a0ab57826494e6caef7fd0a402d29950ad149b1674c7ae24d33df806e37` |
| `learner/ee799a5cb57.json` | `0e16b370d10be74cc4ca06c4649808c848613f7a0462d577cbd6182e122f3126` |
| `learner/ef6906243da.json` | `5d2fdeb6d46a67d22b8e48e0953316f39d39bc4ee4102cf7e25b4395ba1f7ee2` |
| `learner/efd8d946fc4.json` | `f3a5eec4ce75100e87005b467eda2ede98962c3d21e43c91f9a75b90594d2197` |
| `learner/effc94c7633.json` | `8062ed510d3e9aa43dafb572e3d16e04fc35977d89617556f49020d88b5225a8` |
| `manifest.private.json` | `b1f6eacbf1559c655a77623315c52948fded99df1e8f6a0667e9a40dfd346134` |
| `manifest.public.json` | `d35a6b7e9089ca2ebbbd6e2d5b49433a30d1953575b442a4658917c0b565d976` |
