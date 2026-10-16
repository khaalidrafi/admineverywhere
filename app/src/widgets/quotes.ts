/** ~30 curated quotes on business, rizq (provision), halal earning and
 *  taqwa — from the Qur'an, authentic Sunnah, and the early generations
 *  (Aslaf). Sources cited with each quote; popular-but-unverified
 *  attributions are marked "attributed".
 */
export interface Quote {
  text: string;
  source: string;
}

export const QUOTES: Quote[] = [
  // ---- Qur'an ----
  { text: "And whoever is mindful of Allah — He will make a way out for him, and provide for him from where he does not expect.", source: "Qur'an 65:2–3" },
  { text: "And whoever puts their trust in Allah, then He is sufficient for them.", source: "Qur'an 65:3" },
  { text: "There is no creature on earth but that upon Allah is its provision.", source: "Qur'an 11:6" },
  { text: "And that man will only have what he strives for.", source: "Qur'an 53:39" },
  { text: "Allah has permitted trade and forbidden interest.", source: "Qur'an 2:275" },
  { text: "Give full measure, and do not be of those who cause loss.", source: "Qur'an 26:181" },
  { text: "Woe to those who give less than due — those who, when they take a measure from people, take in full, but when they give by measure or weight, they give less.", source: "Qur'an 83:1–3" },
  { text: "But seek, through that which Allah has given you, the home of the Hereafter; and do not forget your share of the present world.", source: "Qur'an 28:77" },
  { text: "Indeed, with hardship comes ease.", source: "Qur'an 94:6" },
  { text: "And when the prayer has been concluded, disperse within the land and seek the bounty of Allah.", source: "Qur'an 62:10" },
  { text: "It is He who made the earth manageable for you — so walk among its slopes and eat of His provision.", source: "Qur'an 67:15" },
  { text: "And whatever blessing you have — it is from Allah.", source: "Qur'an 16:53" },
  { text: "Whatever you spend — He will replace it; and He is the best of providers.", source: "Qur'an 34:39" },
  { text: "And those who strive for Us — We will surely guide them to Our ways.", source: "Qur'an 29:69" },

  // ---- Sunnah ----
  { text: "The trustworthy, honest merchant will be with the prophets, the truthful, and the martyrs.", source: "Prophet ﷺ — Tirmidhi" },
  { text: "Whoever cheats us is not one of us.", source: "Prophet ﷺ — Muslim" },
  { text: "The upper hand that gives is better than the lower hand that takes.", source: "Prophet ﷺ — Bukhari & Muslim" },
  { text: "Richness is not an abundance of worldly goods; richness is contentment of the soul.", source: "Prophet ﷺ — Bukhari & Muslim" },
  { text: "There are two blessings which many people waste: health and free time.", source: "Prophet ﷺ — Bukhari" },
  { text: "Allah loves that when one does a deed, he does it with excellence.", source: "Prophet ﷺ — al-Bayhaqi" },
  { text: "Charity does not decrease wealth.", source: "Prophet ﷺ — Muslim" },
  { text: "The most beloved of deeds to Allah are the most consistent, even if small.", source: "Prophet ﷺ — Bukhari & Muslim" },
  { text: "The buyer and seller have the option to cancel as long as they have not separated.", source: "Prophet ﷺ — Bukhari & Muslim" },
  { text: "The best of people are those most beneficial to people.", source: "Prophet ﷺ — al-Mu'jam al-Awsat (hasan)" },
  { text: "Take advantage of five before five: your youth before old age, your health before sickness, your wealth before poverty, your free time before becoming busy, and your life before your death.", source: "Prophet ﷺ — al-Hakim" },
  { text: "Every act of kindness is charity.", source: "Prophet ﷺ — Bukhari & Muslim" },
  { text: "The strong believer is better and more beloved to Allah than the weak believer, though in each there is good.", source: "Prophet ﷺ — Muslim" },

  // ---- Aslaf (early generations) ----
  { text: "Account yourselves before you are brought to account, and weigh yourselves before you are weighed.", source: "Umar ibn al-Khattab (ra)" },
  { text: "We are a people whom Allah honored with Islam; whenever we seek honor in anything else, Allah will humble us.", source: "Umar ibn al-Khattab (ra)" },
  { text: "The worth of every person lies in what he does well.", source: "attributed to Ali ibn Abi Talib (ra)" },
];

export function randomQuote(excludeIndex = -1): number {
  if (QUOTES.length <= 1) return 0;
  let i = Math.floor(Math.random() * QUOTES.length);
  while (i === excludeIndex) {
    i = Math.floor(Math.random() * QUOTES.length);
  }
  return i;
}
