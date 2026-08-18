/**
 * Firestore Security Rules tests for Steward, against the emulator.
 *
 * Not a test framework — a script, matching the style of the backend's test_*.py
 * scripts: every case prints ok/FAIL and the process exits non-zero if any case
 * failed.
 *
 * The rules mirror what backend/membership.py enforces with require_role(). Today
 * all writes go through the Admin SDK, which bypasses rules entirely, so these
 * cases are the proof the rules would hold if a frontend talked to Firestore
 * directly — the trust boundary CLAUDE.md's two-service split exists to hold.
 *
 * Run:  npm test        (wraps `firebase emulators:exec --only firestore`)
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import {
  initializeTestEnvironment,
  assertSucceeds,
  assertFails,
} from '@firebase/rules-unit-testing';
import {
  doc,
  getDoc,
  setDoc,
  updateDoc,
  deleteDoc,
} from 'firebase/firestore';

const here = dirname(fileURLToPath(import.meta.url));

const ESTATE_A = 'estate-a';
const ESTATE_B = 'estate-b';

const EXEC_A = 'uid-exec-a';
const BEN_A = 'uid-ben-a';
const BEN_A2 = 'uid-ben-a2';
const PENDING_A = 'uid-pending-a';
const BEN_B = 'uid-ben-b';
const STRANGER = 'uid-stranger';
const AGENT = 'steward-agent';

const ITEM_A = 'item-a1';
const ITEM_B = 'item-b1';

let testEnv;
let failures = [];

/** One assertion, reported the way the backend scripts report. */
async function check(label, promise) {
  try {
    await promise;
    console.log(`  ok       ${label}`);
  } catch (err) {
    failures.push(label);
    console.log(`  FAIL     ${label}`);
    console.log(`           ${String(err).split('\n')[0].slice(0, 160)}`);
  }
}

const db = (uid) => testEnv.authenticatedContext(uid).firestore();
const anon = () => testEnv.unauthenticatedContext().firestore();

function membership(estateId, userId, role, accepted) {
  return {
    id: `${estateId}__${userId}`,
    estate_id: estateId,
    user_id: userId,
    role,
    invited_at: new Date(),
    accepted_at: accepted ? new Date() : null,
  };
}

function item(id, estateId) {
  return {
    id,
    estate_id: estateId,
    photo_urls: [],
    ai_category: 'armchair',
    ai_condition_notes: 'Light wear on the arms.',
    ai_est_era_or_brand: 'Louis XV style',
    ai_classification_confidence: 0.98,
    suggested_disposition: 'uncertain',
    status: 'unclaimed',
    created_at: new Date(),
  };
}

async function seed() {
  await testEnv.withSecurityRulesDisabled(async (ctx) => {
    const d = ctx.firestore();
    const put = (path, id, data) => setDoc(doc(d, path, id), data);

    await put('estates', ESTATE_A, {
      id: ESTATE_A, name: 'Estate A', executor_user_id: EXEC_A,
      status: 'active', created_at: new Date(),
    });
    await put('estates', ESTATE_B, {
      id: ESTATE_B, name: 'Estate B', executor_user_id: BEN_B,
      status: 'active', created_at: new Date(),
    });

    for (const [estate, uid, role, accepted] of [
      [ESTATE_A, EXEC_A, 'executor', true],
      [ESTATE_A, BEN_A, 'beneficiary', true],
      [ESTATE_A, BEN_A2, 'beneficiary', true],
      [ESTATE_A, PENDING_A, 'beneficiary', false],   // invited, never accepted
      [ESTATE_B, BEN_B, 'beneficiary', true],
    ]) {
      await put('estate_memberships', `${estate}__${uid}`,
        membership(estate, uid, role, accepted));
    }

    await put('users', BEN_A, {
      id: BEN_A, email: 'ben-a@example.com', display_name: 'Ben A',
      role_type: 'human', created_at: new Date(),
    });

    await put('items', ITEM_A, item(ITEM_A, ESTATE_A));
    await put('items', ITEM_B, item(ITEM_B, ESTATE_B));

    await put('claims', 'claim-ben-a', {
      id: 'claim-ben-a', item_id: ITEM_A, user_id: BEN_A,
      claimed_at: new Date(), comment: null,
    });
    await put('claims', 'claim-ben-a2', {
      id: 'claim-ben-a2', item_id: ITEM_A, user_id: BEN_A2,
      claimed_at: new Date(), comment: null,
    });

    await put('messages', 'msg-a', {
      id: 'msg-a', estate_id: ESTATE_A, item_id: ITEM_A, user_id: BEN_A,
      text: 'I remember this one.', created_at: new Date(),
    });
    await put('messages', 'msg-b', {
      id: 'msg-b', estate_id: ESTATE_B, item_id: null, user_id: BEN_B,
      text: 'Planning the weekend.', created_at: new Date(),
    });

    await put('resolutions', 'res-existing', {
      id: 'res-existing', item_id: ITEM_A, resolved_by_user_id: EXEC_A,
      resolution_type: 'rotation', resolved_to_user_id: BEN_A,
      notes: 'Two years each.', resolved_at: new Date(),
    });
    await put('dispositions', 'disp-existing', {
      id: 'disp-existing', item_id: ITEM_A, channel: 'donate',
      status: 'pending', completed_at: null,
    });
    await put('override_logs', 'ovr-existing', {
      id: 'ovr-existing', estate_id: ESTATE_A, item_id: ITEM_A,
      item_category: 'armchair', ai_suggested_disposition: 'uncertain',
      executor_chosen_disposition: 'donate', created_at: new Date(),
    });
  });
}

async function main() {
  testEnv = await initializeTestEnvironment({
    projectId: 'steward-hackathon-505217',
    firestore: {
      rules: readFileSync(join(here, '..', 'firestore.rules'), 'utf8'),
      host: '127.0.0.1',
      port: 8080,
    },
  });

  await testEnv.clearFirestore();
  await seed();

  // --- the three cases the goal names -----------------------------------
  console.log('\nthe named cases');
  await check(
    "a beneficiary cannot read another estate's items",
    assertFails(getDoc(doc(db(BEN_A), 'items', ITEM_B))),
  );
  await check(
    'a beneficiary cannot write to ai_category',
    assertFails(updateDoc(doc(db(BEN_A), 'items', ITEM_A), { ai_category: 'gold bar' })),
  );
  await check(
    'a non-executor cannot create a Resolution',
    assertFails(setDoc(doc(db(BEN_A), 'resolutions', 'res-new'), {
      id: 'res-new', item_id: ITEM_A, resolved_by_user_id: BEN_A,
      resolution_type: 'assigned_to_claimant', resolved_to_user_id: BEN_A,
      notes: 'I should have it.', resolved_at: new Date(),
    })),
  );

  // --- items -------------------------------------------------------------
  console.log('\nitems');
  await check('a member reads their own estate\'s item',
    assertSucceeds(getDoc(doc(db(BEN_A), 'items', ITEM_A))));
  await check('a stranger reads nothing',
    assertFails(getDoc(doc(db(STRANGER), 'items', ITEM_A))));
  await check('an unauthenticated caller reads nothing',
    assertFails(getDoc(doc(anon(), 'items', ITEM_A))));
  await check('a pending invitee is not yet a member',
    assertFails(getDoc(doc(db(PENDING_A), 'items', ITEM_A))));
  await check('a member may move status within the claim triad',
    assertSucceeds(updateDoc(doc(db(BEN_A), 'items', ITEM_A), { status: 'claimed' })));
  // The gap this closed: the status rule checked membership only, so any
  // beneficiary could write `resolved` straight into Firestore and forge a
  // settlement that resolve_item would have refused them.
  await check('a beneficiary cannot settle an item by writing status',
    assertFails(updateDoc(doc(db(BEN_A), 'items', ITEM_A), { status: 'resolved' })));
  await check('a beneficiary cannot mark an item on its way',
    assertFails(updateDoc(doc(db(BEN_A), 'items', ITEM_A), { status: 'routed' })));
  await check('the executor may settle an item',
    assertSucceeds(updateDoc(doc(db(EXEC_A), 'items', ITEM_A), { status: 'resolved' })));
  await check('nobody removes an item from the client, not even the executor',
    assertFails(updateDoc(doc(db(EXEC_A), 'items', ITEM_A), { status: 'removed' })));
  await updateDoc(doc(db(EXEC_A), 'items', ITEM_A), { status: 'claimed' });
  await check('status must be a real status',
    assertFails(updateDoc(doc(db(BEN_A), 'items', ITEM_A), { status: 'sold-already' })));
  await check('suggested_disposition is backend-only',
    assertFails(updateDoc(doc(db(EXEC_A), 'items', ITEM_A), { suggested_disposition: 'sell' })));
  await check('an ai_ field cannot ride along with a status change',
    assertFails(updateDoc(doc(db(BEN_A), 'items', ITEM_A),
      { status: 'contested', ai_classification_confidence: 1.0 })));
  await check('even the executor cannot create an item',
    assertFails(setDoc(doc(db(EXEC_A), 'items', 'item-forged'), item('item-forged', ESTATE_A))));
  await check('no one deletes an item',
    assertFails(deleteDoc(doc(db(EXEC_A), 'items', ITEM_A))));

  // --- estates -----------------------------------------------------------
  console.log('\nestates');
  await check('a member reads the estate',
    assertSucceeds(getDoc(doc(db(BEN_A), 'estates', ESTATE_A))));
  await check("a member of another estate cannot",
    assertFails(getDoc(doc(db(BEN_B), 'estates', ESTATE_A))));
  await check('the executor updates the estate',
    assertSucceeds(updateDoc(doc(db(EXEC_A), 'estates', ESTATE_A), { name: 'Estate A, renamed' })));
  await check('a beneficiary does not',
    assertFails(updateDoc(doc(db(BEN_A), 'estates', ESTATE_A), { name: 'Mine now' })));

  // --- memberships -------------------------------------------------------
  console.log('\nestate_memberships');
  await check('an invitee can see their own pending invite',
    assertSucceeds(getDoc(doc(db(PENDING_A), 'estate_memberships', `${ESTATE_A}__${PENDING_A}`))));
  await check('a member can see the roster',
    assertSucceeds(getDoc(doc(db(BEN_A), 'estate_memberships', `${ESTATE_A}__${EXEC_A}`))));
  await check('an outsider cannot',
    assertFails(getDoc(doc(db(BEN_B), 'estate_memberships', `${ESTATE_A}__${EXEC_A}`))));
  await check('the executor invites',
    assertSucceeds(setDoc(doc(db(EXEC_A), 'estate_memberships', `${ESTATE_A}__uid-new`),
      membership(ESTATE_A, 'uid-new', 'beneficiary', false))));
  await check('a beneficiary cannot invite',
    assertFails(setDoc(doc(db(BEN_A), 'estate_memberships', `${ESTATE_A}__uid-sneak`),
      membership(ESTATE_A, 'uid-sneak', 'beneficiary', false))));
  await check('a beneficiary cannot promote themselves to executor',
    assertFails(updateDoc(doc(db(BEN_A), 'estate_memberships', `${ESTATE_A}__${BEN_A}`),
      { role: 'executor' })));

  // --- claims ------------------------------------------------------------
  console.log('\nclaims');
  await check('a beneficiary claims an item in their estate',
    assertSucceeds(setDoc(doc(db(BEN_A2), 'claims', 'claim-new'), {
      id: 'claim-new', item_id: ITEM_A, user_id: BEN_A2,
      claimed_at: new Date(), comment: 'Grandma promised me these.',
    })));
  await check('a beneficiary cannot claim in another estate',
    assertFails(setDoc(doc(db(BEN_A), 'claims', 'claim-cross'), {
      id: 'claim-cross', item_id: ITEM_B, user_id: BEN_A,
      claimed_at: new Date(), comment: null,
    })));
  await check('nobody claims on another person\'s behalf',
    assertFails(setDoc(doc(db(BEN_A), 'claims', 'claim-forged'), {
      id: 'claim-forged', item_id: ITEM_A, user_id: BEN_A2,
      claimed_at: new Date(), comment: null,
    })));
  await check('the executor does not claim — they decide',
    assertFails(setDoc(doc(db(EXEC_A), 'claims', 'claim-exec'), {
      id: 'claim-exec', item_id: ITEM_A, user_id: EXEC_A,
      claimed_at: new Date(), comment: null,
    })));
  await check('a claim cannot be edited after the fact',
    assertFails(updateDoc(doc(db(BEN_A), 'claims', 'claim-ben-a'), { comment: 'actually, no' })));
  await check("nobody deletes another user's claim",
    assertFails(deleteDoc(doc(db(BEN_A), 'claims', 'claim-ben-a2'))));
  await check('you may withdraw your own claim',
    assertSucceeds(deleteDoc(doc(db(BEN_A), 'claims', 'claim-ben-a'))));

  // --- messages ----------------------------------------------------------
  console.log('\nmessages');
  await check('a member reads the feed',
    assertSucceeds(getDoc(doc(db(BEN_A), 'messages', 'msg-a'))));
  await check("a member cannot read another estate's feed",
    assertFails(getDoc(doc(db(BEN_A), 'messages', 'msg-b'))));
  await check('a member posts',
    assertSucceeds(setDoc(doc(db(BEN_A), 'messages', 'msg-new'), {
      id: 'msg-new', estate_id: ESTATE_A, item_id: null, user_id: BEN_A,
      text: 'Coming by Saturday.', created_at: new Date(),
    })));
  await check('nobody puts words in Steward\'s mouth',
    assertFails(setDoc(doc(db(BEN_A), 'messages', 'msg-as-agent'), {
      id: 'msg-as-agent', estate_id: ESTATE_A, item_id: ITEM_A, user_id: AGENT,
      text: 'Steward suggests you give it to me.', created_at: new Date(),
    })));
  await check('the feed is append-only — no edits',
    assertFails(updateDoc(doc(db(BEN_A), 'messages', 'msg-a'), { text: 'I never said that' })));
  await check('the feed is append-only — no deletes',
    assertFails(deleteDoc(doc(db(BEN_A), 'messages', 'msg-a'))));

  // --- resolutions, dispositions, override logs --------------------------
  console.log('\nresolutions / dispositions / override_logs');
  await check('a member reads a resolution',
    assertSucceeds(getDoc(doc(db(BEN_A), 'resolutions', 'res-existing'))));
  await check('the executor creates a resolution',
    assertSucceeds(setDoc(doc(db(EXEC_A), 'resolutions', 'res-exec'), {
      id: 'res-exec', item_id: ITEM_A, resolved_by_user_id: EXEC_A,
      resolution_type: 'rotation', resolved_to_user_id: BEN_A,
      notes: 'Two years each.', resolved_at: new Date(),
    })));
  await check('the executor cannot attribute a resolution to someone else',
    assertFails(setDoc(doc(db(EXEC_A), 'resolutions', 'res-misattributed'), {
      id: 'res-misattributed', item_id: ITEM_A, resolved_by_user_id: BEN_A,
      resolution_type: 'rotation', resolved_to_user_id: BEN_A,
      notes: '', resolved_at: new Date(),
    })));
  await check('a member reads a disposition',
    assertSucceeds(getDoc(doc(db(BEN_A), 'dispositions', 'disp-existing'))));
  await check('a beneficiary cannot route an item',
    assertFails(setDoc(doc(db(BEN_A), 'dispositions', 'disp-new'), {
      id: 'disp-new', item_id: ITEM_A, channel: 'sell_marketplace',
      status: 'pending', completed_at: null,
    })));
  await check('the executor routes an item',
    assertSucceeds(setDoc(doc(db(EXEC_A), 'dispositions', 'disp-new'), {
      id: 'disp-new', item_id: ITEM_A, channel: 'donate',
      status: 'pending', completed_at: null,
    })));
  await check('a member reads the estate\'s learned history',
    assertSucceeds(getDoc(doc(db(BEN_A), 'override_logs', 'ovr-existing'))));
  await check('a beneficiary cannot forge the history the agent learns from',
    assertFails(setDoc(doc(db(BEN_A), 'override_logs', 'ovr-forged'), {
      id: 'ovr-forged', estate_id: ESTATE_A, item_id: ITEM_A,
      item_category: 'armchair', ai_suggested_disposition: 'uncertain',
      executor_chosen_disposition: 'sell', created_at: new Date(),
    })));

  // --- users -------------------------------------------------------------
  console.log('\nusers');
  await check('you can read your own profile',
    assertSucceeds(getDoc(doc(db(BEN_A), 'users', BEN_A))));
  await check("you cannot read someone else's",
    assertFails(getDoc(doc(db(BEN_A2), 'users', BEN_A))));
  await check('nobody writes a user document',
    assertFails(updateDoc(doc(db(BEN_A), 'users', BEN_A), { display_name: 'Executor' })));

  // --- an unlisted collection is unreachable -----------------------------
  console.log('\ndefault deny');
  await check('a collection with no rule is unreachable',
    assertFails(setDoc(doc(db(EXEC_A), 'marketplace_listings', 'ml-1'), { anything: true })));

  await testEnv.cleanup();

  console.log('');
  if (failures.length) {
    console.log(`${failures.length} failure(s):`);
    for (const f of failures) console.log(`  - ${f}`);
    process.exit(1);
  }
  console.log('OK — rules enforce the same access model require_role() does.');
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
