# Final battery freeze (Plan 5)

Frozen 2026-10-16 with `oa eval freeze --split final` before any learner run. The private files live in
`benchmarks/final/battery/` (git-ignored); only their hashes and the learner-projected manifest are committed here.
`oa eval run --split final` re-hashes every file against `battery_final.hashes.json` and refuses on any mismatch.

- Generator: `battery-v2.1`, scoring `score-v2.1`, tolerance 1/2
- Generator code commit: `76e3e43f69fa6a234175e081cd3209f7b3858176`
- Seed base: 170000 (development: 110000)
- `manifest.private.json` sha256: `395b0dface8eceac7a9fc256544b3847c6f64c3b400502fb7117e1b196c97284`
- `manifest.public.json` sha256: `24d5509696aaac36080b89d46559f49028341bcc247926dda882950722116347`
- Episodes: 36 (catalogue 8, beyond 8, inconsistent 4, unsupported 4, sequential 12) plus 3 real-file episodes on
  `benchmarks/final/drawio/f1-f3` (bytes hashed and matched to `docs/corpus/drawio_provenance.md`; contents not parsed).

## Public manifest (opaque ids)

```json
{
 "episodes": [
  "e00919ea6b5",
  "e037a0c1096",
  "e05703611e5",
  "e059c27c6cf",
  "e17d289b556",
  "e1943411111",
  "e2fb1adc733",
  "e31a4a7af18",
  "e384fa79f0f",
  "e3de5d8b237",
  "e446cffc41b",
  "e4699830ece",
  "e46c491bbc4",
  "e4eda2f9da5",
  "e5581f5d950",
  "e5e9fd4cb90",
  "e62fbff4d9e",
  "e63af6b8bbe",
  "e66d1885679",
  "e73df46d6b6",
  "e7ef825d8fe",
  "e8584a4d513",
  "e859f47f414",
  "e8bcdb904b7",
  "e8caec6f137",
  "e9e3be306c2",
  "ea2c64998e9",
  "eb5a11da194",
  "eca6da164b4",
  "ecb1123c591",
  "ed2086ff666",
  "ed30ea640eb",
  "ed332f737b7",
  "ede6ea4b280",
  "ee119f50260",
  "efa023baece"
 ],
 "split": "final"
}
```

## File hashes

| file | sha256 |
|---|---|
| `episodes/e00919ea6b5.private.json` | `333b7f70cb1c142ebcb6cf06c77f0aa4f595a843a7f6aa7b9348ddc8c933c997` |
| `episodes/e037a0c1096.private.json` | `a9d0a13dae8bad8cab71c4e537e93a12c8b2af327ea05a2523652d9586af5709` |
| `episodes/e05703611e5.private.json` | `332ebc9550941b08e41fd19ea53e988bc967856625537cc4fe756d46c9055315` |
| `episodes/e059c27c6cf.private.json` | `1bcea5787b2e8c01184652f33d9ee27723ee7acc5c790b8ab8966a661b6ff87b` |
| `episodes/e17d289b556.private.json` | `d571b7897567cdc753de9f42739f47317b67462efad8d16fbfab27880abbbbf7` |
| `episodes/e1943411111.private.json` | `81b424ccc1eacfa79ac5a2c4aa419da98840b029224ec3bb058a394e15a3e57e` |
| `episodes/e2fb1adc733.private.json` | `a781a5820c59bbbe24b4583825aca3c27f78983daefdb1db2e8fa253f824b28e` |
| `episodes/e31a4a7af18.private.json` | `0d960017d162e49928448963f4eb0fc632663d84a481e243dda93b069470a75b` |
| `episodes/e384fa79f0f.private.json` | `f9be526021bdc3e30dc6ef534d078b0d3a266806f8cc4bd67a8f7598c2f69fed` |
| `episodes/e3de5d8b237.private.json` | `b0a3f14b9816095b22c9dc1518c7f6f4b253b072ac0965298e97de4b40d34466` |
| `episodes/e446cffc41b.private.json` | `012b8e1c906f768c339724c5c5aeef4ba05e828bcc40dbca55cdb64b2dd26c1a` |
| `episodes/e4699830ece.private.json` | `83e2436403729a79b5a6bd7fea20ad803b225d3d484fbd282c857850414b1b93` |
| `episodes/e46c491bbc4.private.json` | `ad2e5a9d9622060e12fe848e8dadaf2e9f299289d6a82f55e55f0db2af372013` |
| `episodes/e4eda2f9da5.private.json` | `29f929ec8bbe568ffe543096b70b11e9c7bbc5d593d60088c9ee50a4b5cfbb5a` |
| `episodes/e5581f5d950.private.json` | `c52670a851bd02e7d10451f1236e2673aeba9b1bb472be948a6c7557d2ae142d` |
| `episodes/e5e9fd4cb90.private.json` | `fb18432df2c5003fc631c199cd033f19c4e0102e5c422f75c64d73e4c5e6e830` |
| `episodes/e62fbff4d9e.private.json` | `11e5becb61dc8e7d0b30735b46f6c837e708715650b1a950129bceab6d87b595` |
| `episodes/e63af6b8bbe.private.json` | `bea9d4461ef2f91906890ae412fa9c921eac254bfe034987dacd6301e677f7f8` |
| `episodes/e66d1885679.private.json` | `597182a8bfa576c69199572fc26ff77f1bfe32e9acfbbe5ba70cf2674731dd09` |
| `episodes/e73df46d6b6.private.json` | `2d7f925153fa8bd2bc04eb95375e8d29690ebc359a5b44bf065015b31dff50e0` |
| `episodes/e7ef825d8fe.private.json` | `fd645f331f159c08518334ac3107adc8fe6b3a71a653e1860483c50ee47a7fd3` |
| `episodes/e8584a4d513.private.json` | `82ec42e5480b42099954c2c99498a5b92266b73af1854f078191b9400bb88d74` |
| `episodes/e859f47f414.private.json` | `11353371708a6b47920ece3b8126eb7fbe77eca2a56bc7d625cb187ecbcbef9a` |
| `episodes/e8bcdb904b7.private.json` | `7c3b3f79d4107bc452c935ad876031a9d347f2a0a91cccc302c699446fa844fe` |
| `episodes/e8caec6f137.private.json` | `0b73220ae3bc241978ee470600b464467ff4f38051e87cc69e100cb171fefedd` |
| `episodes/e9e3be306c2.private.json` | `dc6ec971bbf9f491f8d2efc5eb283615baf999ceb8149468c2f0a55ad5aecbbb` |
| `episodes/ea2c64998e9.private.json` | `3272207a39dd49c1856135b57d671b25687468424f9f06f3e1958cf77841509f` |
| `episodes/eb5a11da194.private.json` | `1d27fa95a378707d0791988fd11a60ca24703f4ee5147fcb7c2fe70e16c36163` |
| `episodes/eca6da164b4.private.json` | `b698a741bfe69a80d4afdcc196869b68ac6010f1a834704f1478c0e7dfc9c1c9` |
| `episodes/ecb1123c591.private.json` | `2fa7ad31f590b39e200b631eaacc9fa9ca040f04b2a73b5849941055bc7da543` |
| `episodes/ed2086ff666.private.json` | `466ebdc95aafab6f8417e4d5cf8686ec59ff249c104cd706d3be7ec411bb2a4e` |
| `episodes/ed30ea640eb.private.json` | `f0d50fa1a3abdab60f5afd3ea33e020af176d00382f2ca2ad01fa227b6ef2d13` |
| `episodes/ed332f737b7.private.json` | `a58a28c79c4e6485359ed4e0cd8b4464afd4d4950bd698f0a1b4618d22233875` |
| `episodes/ede6ea4b280.private.json` | `3493b83dbb5e7584ef4c73116ed3a822735734526520bb94fa682477bba38849` |
| `episodes/ee119f50260.private.json` | `ab7d48fbae74d2d615d463a440c121bee590c0ece6f58097f1bdda03577a2f75` |
| `episodes/efa023baece.private.json` | `1826d1bd74d3a73a57102e7f474cf29e09688f6252878939a2d235aeb79e3a92` |
| `learner/e00919ea6b5.json` | `81e15fb10db7ce95b9b1e32133ba1d336f51724934191344d6f195263bbea098` |
| `learner/e037a0c1096.json` | `1c134237a0b9dcfc7b679c52efc47fe791bf9e48d7ebd8af1d188600c3912cd2` |
| `learner/e05703611e5.json` | `d0f0a9d405acff37a0e1df3df233453ff31ee2a055beacaf14ee2e929e734099` |
| `learner/e059c27c6cf.json` | `a6b440940b7997de4898147ab4a126852112443c5dea6b2f1765b40e339643b3` |
| `learner/e17d289b556.json` | `3629b399d3716d031f1523ed0dc45f51c116037c1f9e9aa9b438b9e484201be5` |
| `learner/e1943411111.json` | `34ea7dd9b81205f60614e4724d9357c73e00e002059b93a554d7bf9701705307` |
| `learner/e2fb1adc733.json` | `6db324e698982a48bde713255d9e03436c49c21d123404b315fccbf3e8d2ee18` |
| `learner/e31a4a7af18.json` | `2b5bf57358be7d91150f61ec9837156803a1ff8dbb293eeda350bdd9296c28eb` |
| `learner/e384fa79f0f.json` | `8abefdf2470695c78d9b09245b3bdec45688ff7202ae9bcde2404a7b9f50cb34` |
| `learner/e3de5d8b237.json` | `8d6e3a175ec552c8c12c9a6100895cad1c357f11a7838d312cf01c64bbd1f53e` |
| `learner/e446cffc41b.json` | `513c7ee6693f5c4c3cfbd1c12ab22e0bd3261686642f0babc349589fb88f1eb4` |
| `learner/e4699830ece.json` | `ebf8b1f70c46f65178bb0ff7595e03c8bba137fb941277fedbc5db78966267d4` |
| `learner/e46c491bbc4.json` | `4d5d63547e744a04fa0726c04d2bfb9f3a27d47b7017d66fe2e7b60e4d6338a2` |
| `learner/e4eda2f9da5.json` | `4a8fc78c2ce811fe342415a4d92adb8d159eaa3f9a3d793b3efefbb33a600c02` |
| `learner/e5581f5d950.json` | `c1ee1956c6077dedb30ba74b88f8400524eed4f61d17bfe60203d7852728b177` |
| `learner/e5e9fd4cb90.json` | `473bc9e8078dde061cdc43199ecf1ac150d38047b88c8088df4b466fcf5d5f13` |
| `learner/e62fbff4d9e.json` | `4e53ae3b1973ad2d75f18e1671d7f03d1844e6ce0f179f83bced9ec3c5c92d09` |
| `learner/e63af6b8bbe.json` | `47afe6903681843ec8c9338b1e18f84c40602017c29d9ae205bd21d2b42bb6cb` |
| `learner/e66d1885679.json` | `0013ecefe77dc4bbbb96aaf335ac328f39996c19accedfb62e185025a0cae7f3` |
| `learner/e73df46d6b6.json` | `86692fd3f45a6cd6903420b68cea6001be90abd41c5af5bd1dde5be25b7fbc72` |
| `learner/e7ef825d8fe.json` | `f6d10788d86f9e78e60cf9309c85e07d3a113f0352631111bc53475aa3f223be` |
| `learner/e8584a4d513.json` | `36b7c50ef6ad3e15c7eff1e373bfaf7add2d087911c6bc74381aac81fe83a7f7` |
| `learner/e859f47f414.json` | `26723813861ef39a35ab59ce90c4e72ff935c1faf0582e1c601452a64725b9b8` |
| `learner/e8bcdb904b7.json` | `f99039b7faea6f98f4a3c42b50ffd740b2e5864b4fd975dc399415c68fafe16d` |
| `learner/e8caec6f137.json` | `0271add665c462905661182b89f6f3b1aa7e553b0c005b71d99c7195f29977c9` |
| `learner/e9e3be306c2.json` | `0da7b8b19ece4a486953833dba223fc5a4de2538c95ae0d092abe6f8bc6ee54f` |
| `learner/ea2c64998e9.json` | `829e12695802dbfa35a98763b2a68d1febbeb05e00834e9deda1cb3bf0bddaea` |
| `learner/eb5a11da194.json` | `74418a0950b431fccc3ac5781fa78ca30a3d28f0b0675a232b9728329bae886a` |
| `learner/eca6da164b4.json` | `4b01b5acf59028691e29dbffe8298500b413e429540d541796d5194641f14dcf` |
| `learner/ecb1123c591.json` | `56279d09b4e484c3d1b1e3f04b1e2e4e333d9caf36e1afc7d0f199a588916da4` |
| `learner/ed2086ff666.json` | `76ecf836e8ce720b1ce0aae66dda742eafd1ca30f69a56bfdffaaed6c6fa6065` |
| `learner/ed30ea640eb.json` | `fadfb5c2eccec8a5a0ec0b12c4f8daf4d86270fb99fda4b40c9bb3c1a0d12595` |
| `learner/ed332f737b7.json` | `e247f69159167f73e023175b918e7215c8b34e040a3a9285d78d5aead8b353f0` |
| `learner/ede6ea4b280.json` | `27c191d20b203c360e6c9a9dcedfc8b5135496812e0e02d687eb2b0c1675e75f` |
| `learner/ee119f50260.json` | `ef15436f3b80cae859670a5e94510df6426e4d22b02e95d9af402df1a51e2a11` |
| `learner/efa023baece.json` | `c2d864708cd0cfffeddbbe6c02b637dea6c1fd7ccf480cb39cacd240484e6af4` |
| `manifest.private.json` | `395b0dface8eceac7a9fc256544b3847c6f64c3b400502fb7117e1b196c97284` |
| `manifest.public.json` | `24d5509696aaac36080b89d46559f49028341bcc247926dda882950722116347` |
