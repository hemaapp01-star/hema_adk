/* eslint-disable max-len */
/* eslint-disable require-jsdoc */
import { onCall, HttpsError } from "firebase-functions/v2/https";
import { onDocumentCreated, onDocumentUpdated, onDocumentWritten } from "firebase-functions/v2/firestore";
import { defineSecret } from "firebase-functions/params";
import * as logger from "firebase-functions/logger";
import axios from "axios";
import admin from "firebase-admin";
import * as geofire from "geofire-common";
import nodemailer from "nodemailer";

admin.initializeApp();

const googlePlacesApiKey = defineSecret("GOOGLE_PLACES_API_KEY");

export async function sendAdminNotification(message, subject) {
  const adminEmail = "hema.app.01@gmail.com";
  // Fallback to adminEmail if ADMIN_RECEIVER_EMAIL is not set
  const adminReceiverEmail = process.env.ADMIN_RECEIVER_EMAIL || adminEmail;

  // 1. Create the transporter
  const transporter = nodemailer.createTransport({
    service: "gmail",
    auth: {
      user: adminEmail,
      pass: "blxc obzr pevw gtmg", // The 16-character app password
    },
  });

  // 2. Define the email content
  const mailOptions = {
    from: `"Hema Provider Verification Service" <${adminEmail}>`,
    to: adminReceiverEmail,
    subject: subject || "🚨 Input Needed: Hema Admin Alert",
    html: `
      <div style="font-family: sans-serif; border: 1px solid #eee; padding: 20px;">
        <h2 style="color: #d32f2f;">Admin Action Required</h2>
        <p>A new user has requested assistance that requires your manual input.</p>
        <hr>
        <p><strong>Details:</strong> ${message || 'No details provided'}</p>
        <a href="https://your-admin-dashboard.com" 
           style="background: #d32f2f; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
           Open Admin Portal
        </a>
      </div>
    `,
  };

  // 3. Send it
  try {
    await transporter.sendMail(mailOptions);
    logger.info("Notification sent to admin.");
    return true;
  } catch (error) {
    logger.error("Failed to send email:", error);
    return false;
  }
}

/**
 * STEP 1: Get Autocomplete suggestions.
 * Broadens search for Nigeria by using valid Primary Types.
 */
export const googlePlacesAutocomplete = onCall(
  {
    secrets: [googlePlacesApiKey],
  },
  async (request) => {
    try {
      const { input, locationType, regionCode, cityContext } = request.data;
      const apiKey = googlePlacesApiKey.value();

      if (!input) throw new HttpsError("invalid-argument", "Input required.");

      const requestBody = {
        input: locationType === "neighborhood" ?
          `${input}, ${cityContext}` : input,
        includedRegionCodes: [regionCode ? regionCode.toLowerCase() : "ng"],
        languageCode: "en",
      };

      // --- TYPE MAPPING LOGIC ---
      let types = [];
      if (locationType === "city") {
        types = ["locality"];
      } else if (locationType === "neighborhood") {
        // 'neighborhood' and 'sublocality' are valid Table B types
        types = ["neighborhood", "sublocality"];
      } else if (locationType === "facility") {
        // 'hospital' and 'doctor' are valid Table A types.
        // 'medical_clinic' is NOT a primary type in v1.
        types = ["hospital", "doctor", "pharmacy"];
      } else {
        /** * IMPORTANT: For street addresses or general searches, we omit
         * includedPrimaryTypes entirely. This allows Google to return
         * addresses, landmarks, and businesses.
         */
        types = [];
      }

      if (types.length > 0) {
        requestBody.includedPrimaryTypes = types;
      }

      logger.info("Places API v1 Request", { body: requestBody });

      const response = await axios.post(
        "https://places.googleapis.com/v1/places:autocomplete",
        requestBody,
        {
          headers: {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": apiKey,
            "X-Goog-FieldMask": "suggestions.placePrediction.placeId," +
              "suggestions.placePrediction.text",
          },
        },
      );

      const suggestions = (response.data.suggestions || []).map((s) => ({
        placeId: s.placePrediction.placeId,
        description: s.placePrediction.text.text,
      }));

      return { suggestions };
    } catch (error) {
      // Detailed logging to find the exact field causing errors
      logger.error("Autocomplete Error", {
        message: error.message,
        details: (error.response && error.response.data &&
          error.response.data.error) || "No extra details",
      });
      throw new HttpsError("internal", (error.response &&
        error.response.data && error.response.data.error &&
        error.response.data.error.message) || error.message);
    }
  },
);

/**
 * STEP 2: Fetch Details (Lat/Long)
 */
export const getPlaceDetails = onCall(
  {
    secrets: [googlePlacesApiKey],
  },
  async (request) => {
    try {
      const { placeId } = request.data;
      const apiKey = googlePlacesApiKey.value();

      if (!placeId) {
        throw new HttpsError("invalid-argument", "placeId required.");
      }

      const response = await axios.get(
        `https://places.googleapis.com/v1/places/${placeId}`,
        {
          headers: {
            "X-Goog-Api-Key": apiKey,
            "X-Goog-FieldMask": "id,location,displayName",
          },
        },
      );

      const result = response.data;
      if (!result.location) {
        throw new HttpsError("not-found", "No coordinates.");
      }

      return {
        lat: result.location.latitude,
        lng: result.location.longitude,
        name: (result.displayName && result.displayName.text) || "",
      };
    } catch (error) {
      logger.error("Place Details Error", error.message);
      throw new HttpsError("internal", error.message);
    }
  },
);

export const deleteUser = onCall(async (request) => {
  try {
    const userId = request.auth && request.auth.uid;

    if (!userId) {
      throw new HttpsError(
        "unauthenticated",
        "User must be authenticated to delete their account.",
      );
    }

    logger.info(`Starting account deletion for user: ${userId}`);

    const db = admin.firestore();
    const auth = admin.auth();

    // Fetch user details before deletion
    const userDoc = await db.collection("users").doc(userId).get();
    const userData = userDoc.exists ? userDoc.data() : { uid: userId, error: "User document not found" };
    await sendAdminNotification(JSON.stringify(userData, null, 2), "Account Deletion");

    // Mark user document for deletion (scheduled for 30 days)
    const deletionDate = new Date();
    deletionDate.setDate(deletionDate.getDate() + 30);

    await db.collection("users").doc(userId).update({
      markedForDeletion: true,
      deletionScheduledAt: admin.firestore.Timestamp.fromDate(deletionDate),
      updatedAt: admin.firestore.FieldValue.serverTimestamp(),
    });

    // Delete donor documents (daytime and nighttime)
    const donorDaytimeRef = db.collection("donors").doc(`${userId}_daytime`);
    const donorNighttimeRef = db.collection("donors")
      .doc(`${userId}_nighttime`);

    await Promise.all([
      donorDaytimeRef.delete(),
      donorNighttimeRef.delete(),
    ]);

    // Delete healthcare provider document if exists
    const providerDoc = await db.collection("healthcare_providers")
      .doc(userId).get();
    if (providerDoc.exists) {
      await providerDoc.ref.delete();
    }

    // Delete user's blood requests
    const requestsSnapshot = await db
      .collection("blood_requests")
      .where("requesterId", "==", userId)
      .get();

    const requestDeletions = requestsSnapshot.docs.map((doc) =>
      doc.ref.delete());
    await Promise.all(requestDeletions);

    // Delete Firebase Auth user
    await auth.deleteUser(userId);

    logger.info(`Account deletion completed for user: ${userId}. ` +
      "Data will be permanently deleted in 30 days.");

    return {
      success: true,
      message: "Account deleted. Your data will be permanently " +
        "removed from our servers in 30 days.",
    };
  } catch (error) {
    logger.error("Error deleting user account:", error);
    throw new HttpsError(
      "internal",
      `Failed to delete account: ${error.message}`,
    );
  }
});

export const onBloodRequestCreated = onDocumentCreated(
  "healthcare_providers/{providerId}/requests/{requestId}",
  async (event) => {
    const requestData = event.data.data();
    const providerId = event.params.providerId;
    const requestId = event.params.requestId;

    // Helper: Find matching donors
    async function findMatchingDonors(center, requestedGroups, targetDonorCount) {
      const matchingDonors = new Map();
      let currentRadiusKm = 2;
      const maxRadiusKm = 50;
      const stepKm = 2;
      let expandedToMax = false;

      logger.info(`Starting donor search. Center: [${center}], Groups: ${requestedGroups}, Target: ${targetDonorCount}`);

      // Standardize requestedGroups to uppercase and trimmed
      const standardizedRequestedGroups = requestedGroups.map((bg) =>
        (typeof bg === "string" ? bg.trim().toUpperCase() : bg),
      );

      while (currentRadiusKm <= maxRadiusKm && matchingDonors.size < targetDonorCount) {
        const bounds = geofire.geohashQueryBounds(center, currentRadiusKm * 1000);
        const queries = bounds.map((b) =>
          admin.firestore().collection("donors")
            .orderBy("geo.geohash")
            .startAt(b[0])
            .endAt(b[1])
            .get(),
        );
        const snapshots = await Promise.all(queries);
        let docsFoundInPass = 0;

        for (const snap of snapshots) {
          docsFoundInPass += snap.docs.length;
          for (const doc of snap.docs) {
            if (matchingDonors.has(doc.id)) continue;
            const donor = doc.data();

            // Standardize donor blood group
            const donorBloodGroup = (donor.bloodGroup || "").trim().toUpperCase();

            if (!donor.geo || !donor.geo.geopoint) {
              logger.warn(`Donor ${doc.id} skipped: Missing geo/geopoint data`);
              continue;
            }

            const distance = geofire.distanceBetween(
              [donor.geo.geopoint.latitude, donor.geo.geopoint.longitude],
              center,
            );

            // Get user document for donor
            const donorUid = donor.uid;
            if (!donorUid) {
              logger.warn(`Donor ${doc.id} skipped: Missing 'uid' field`);
              continue;
            }

            const userDoc = await admin.firestore().collection("users").doc(donorUid).get();
            if (!userDoc.exists) {
              logger.warn(`Donor ${doc.id} skipped: User doc ${donorUid} not found`);
              continue;
            }
            const userData = userDoc.data();

            if (
              distance <= currentRadiusKm &&
              standardizedRequestedGroups.includes(donorBloodGroup) &&
              donor.isAvailable &&
              userData.fcmToken // Now checks fcmToken in users/{uid}
            ) {
              matchingDonors.set(doc.id, { ...donor, fcmToken: userData.fcmToken, uid: donorUid });
              if (matchingDonors.size >= targetDonorCount) break;
            } else {
              // Log rejection reason for debugging
              if (distance <= currentRadiusKm) {
                if (!standardizedRequestedGroups.includes(donorBloodGroup)) logger.info(`Donor ${doc.id} skipped: Blood Group ${donorBloodGroup} not in ${standardizedRequestedGroups}`);
                else if (!donor.isAvailable) logger.info(`Donor ${doc.id} skipped: Not Available`);
                else if (!userData.fcmToken) logger.info(`Donor ${doc.id} skipped: No FCM Token`);
              }
            }
          }
          if (matchingDonors.size >= targetDonorCount) break;
        }

        logger.info(`Radius ${currentRadiusKm}km: Found ${docsFoundInPass} docs in query, Matched ${matchingDonors.size} total.`);

        if (matchingDonors.size < targetDonorCount) {
          if (currentRadiusKm + stepKm > maxRadiusKm) expandedToMax = true;
          currentRadiusKm += stepKm;
        }
      }
      return { matchingDonors, expandedToMax, currentRadiusKm };
    }

    // Helper: Send notification to requester if no donors found
    async function sendNoDonorNotification(requestData) {
      try {
        const requesterId = requestData.requestedBy;
        const requestTitle = requestData.title || "Blood Request";
        if (requesterId) {
          const userDoc = await admin.firestore().collection("users").doc(requesterId).get();
          if (userDoc.exists) {
            const userData = userDoc.data();
            if (userData && userData.fcmToken) {
              const noDonorMsg = {
                notification: {
                  title: requestTitle,
                  body: "Search completed. No available donor was found within your service area. Please proceed with alternative sourcing.",
                },
                data: {
                  requestId: requestId,
                  notificationType: "NO_DONORS_FOUND",
                },
                tokens: [userData.fcmToken],
              };
              const response = await admin.messaging().sendEachForMulticast(noDonorMsg);
              logger.info(`FCM Response (No Donors): Success=${response.successCount}, Failure=${response.failureCount}`);
              if (response.failureCount > 0) {
                response.responses.forEach((resp) => {
                  if (!resp.success) {
                    logger.error("FCM Error for requester:", resp.error);
                  }
                });
              }
              logger.info(`Notified requester (${requesterId}) of no available donors.`);
            } else {
              logger.info(`Requester (${requesterId}) has no FCM token.`);
            }
          } else {
            logger.info(`Requester user document (${requesterId}) not found.`);
          }
        } else {
          logger.info("No requestedBy field found in request data.");
        }
      } catch (notifyErr) {
        logger.error("Failed to notify requester of no donors.", notifyErr);
      }
    }

    // Helper: Write messages to donors
    async function writeMessagesToDonors(matchingDonors, messageContent) {
      const uniqueUids = new Set();
      matchingDonors.forEach((donor) => {
        if (donor.uid) uniqueUids.add(donor.uid);
      });

      const writePromises = Array.from(uniqueUids)
        .map((uid) => {
          return admin.firestore()
            .collection("users")
            .doc(uid)
            .collection("messages")
            .add({
              role: "request",
              timestamp: admin.firestore.FieldValue.serverTimestamp(),
              content: messageContent,
            });
        });
      await Promise.all(writePromises);
    }

    // Helper: Send push notification to donors
    async function sendDonorNotification(matchingDonors, notificationMessage) {
      if (Array.from(matchingDonors.values()).length > 0) {
        const response = await admin.messaging().sendEachForMulticast(notificationMessage);
        logger.info(`FCM Response: Success=${response.successCount}, Failure=${response.failureCount}`);
        if (response.failureCount > 0) {
          response.responses.forEach((resp, idx) => {
            if (!resp.success) {
              logger.error(`FCM Error for token at index ${idx}:`, resp.error);
            }
          });
        }
      }
    }

    // Helper: Update request with found donors
    async function updateRequestWithFoundDonors(requestRef, donorIds) {
      await requestRef.update({ foundDonors: donorIds });
    }

    try {
      // 1. Fetch Provider Data for the "providerLocation" block
      const providerRef = admin.firestore()
        .collection("healthcare_providers").doc(providerId);
      const providerDoc = await providerRef.get();
      if (!providerDoc.exists) {
        logger.error("Provider document not found");
        return null;
      }
      const providerData = providerDoc.data();
      const providerLoc = providerData.geo;
      const center = [
        providerLoc.geopoint.latitude,
        providerLoc.geopoint.longitude,
      ];
      const requestedGroups = requestData.bloodGroup || [];
      const unitsNeeded = requestData.unitsRequested || 1;
      const targetDonorCount = Math.min(Math.max(unitsNeeded, 3), 5);

      // 2. Find matching donors
      const { matchingDonors, expandedToMax, currentRadiusKm } = await findMatchingDonors(center, requestedGroups, targetDonorCount);

      if (matchingDonors.size === 0) {
        logger.info("No matching donors found.");
        if (expandedToMax || currentRadiusKm > 50) {
          await sendNoDonorNotification(requestData);
        }
        return null;
      }

      // 3. ADK AGENT FILTERING STEP
      let filteredMatchingDonors = matchingDonors;
      try {
        const donorIds = Array.from(matchingDonors.values()).map(d => d.uid);
        const sessionId = requestData.requestedBy;

        // Call the /chat endpoint with donor filtering request
        const filterResponse = await axios.post(
          "https://hema-agent-service-103983913840.us-central1.run.app/chat",
          {
            user_id: sessionId,
            session_id: sessionId,
            message: "Filter donors for blood request",
            context: {
              donor_ids: donorIds,
              requestId,
              providerId,
              bloodGroups: requestedGroups,
              unitsNeeded,
            },
          },
          { timeout: 15000 },
        );

        if (
          filterResponse.status === 200 &&
          filterResponse.data.reply
        ) {
          // Parse the agent's reply to extract filtered donor IDs
          let filteredDonorIds;
          try {
            // Attempt to parse JSON array from reply
            filteredDonorIds = JSON.parse(filterResponse.data.reply);
          } catch (parseError) {
            logger.warn("Failed to parse agent reply as JSON, using original donor list.", parseError);
            filteredDonorIds = donorIds;
          }

          if (Array.isArray(filteredDonorIds)) {
            logger.info(`ADK agent filtered donors: ${filteredDonorIds.length} of ${donorIds.length}`);
            filteredMatchingDonors = new Map();
            for (const donor of matchingDonors.values()) {
              if (filteredDonorIds.includes(donor.uid)) {
                filteredMatchingDonors.set(donor.uid, donor);
              }
            }
          } else {
            logger.warn("ADK agent response not an array, using original donor list.");
          }
        } else {
          logger.warn("ADK agent response invalid, using original donor list.");
        }
      } catch (adkError) {
        logger.error("ADK agent request failed, using original donor list.", adkError);
      }

      if (filteredMatchingDonors.size === 0) {
        logger.info("No donors left after ADK agent filtering.");
        await sendNoDonorNotification(requestData);
        return null;
      }

      // 4. PREPARE DATA FOR WRITES & NOTIFICATIONS
      const requestRef = event.data.ref; // Reference to the request doc
      const messageContent = {
        bloodRequest: {
          bloodGroup: after.bloodGroup,
          component: after.component,
          createdAt: after.createdAt,
          quantity: after.quantity,
          title: after.title,
          urgency: after.urgency,
          organizationName: providerName,
          address: providerData.address || "",
          donorId: donorUid,
          donorName: donorDataMsg.firstName || "",
          id: requestId,
          requestRef: event.data.after.ref,
          providerRef: providerDocSnap.ref,
          organisationName: after.organisationName || providerName || null,
        },
        providerLocation: {
          ...providerData,
          requestRef: event.data.after.ref,
          providerRef: providerDocSnap.ref,
        },
      };
      const tokenArray = Array.from(filteredMatchingDonors.values()).map((d) => d.fcmToken);
      const notificationMessage = {
        notification: {
          title: "Urgent: Blood Donors Needed",
          body: `Emergency request for ${requestedGroups.join(", ")} blood within ${currentRadiusKm}km.`,
        },
        data: {
          requestJson: JSON.stringify({
            requestId: requestId,
            hospitalName: providerData.name || providerData.organisationName,
            bloodGroups: requestedGroups.join(", "),
          }),
        },
        tokens: tokenArray,
      };

      // 5. EXECUTE ALL OPS (Writes + Notifications + Update foundDonors)
      await Promise.all([
        writeMessagesToDonors(filteredMatchingDonors, messageContent),
        sendDonorNotification(filteredMatchingDonors, notificationMessage),
        updateRequestWithFoundDonors(requestRef, Array.from(filteredMatchingDonors.keys())),
      ]);

      logger.info(`Successfully notified and wrote messages for ${filteredMatchingDonors.size} donors.`);
      return null;
    } catch (error) {
      logger.error("Error in donor search/update:", error);
      return null;
    }
  },
);

export const onMatchedDonorAdded = onDocumentUpdated(
  "healthcare_providers/{providerId}/requests/{requestId}",
  async (event) => {
    const before = event.data.before.data();
    const after = event.data.after.data();
    const providerId = event.params.providerId;
    const requestId = event.params.requestId;

    // If matchedDonors field doesn't exist or isn't an array, exit
    if (!Array.isArray(before.matchedDonors) || !Array.isArray(after.matchedDonors)) return null;

    // Find new donor(s) added
    const newDonors = after.matchedDonors.filter((uid) => !before.matchedDonors.includes(uid));
    if (newDonors.length === 0) return null;

    // Get requester info
    const requesterId = after.requestedBy;
    if (!requesterId) return null;
    const userDoc = await admin.firestore().collection("users").doc(requesterId).get();
    if (!userDoc.exists) return null;
    const userData = userDoc.data();
    if (!userData.fcmToken) return null;

    // Fetch provider document to get organizationName
    const providerDocSnap = await admin.firestore().collection("healthcare_providers").doc(providerId).get();
    const providerData = providerDocSnap.exists ? providerDocSnap.data() : {};
    const providerName = providerData.organizationName || providerData.organisationName || providerData.name || "";

    // For each new donor, send notification, create match document, and add message
    for (const donorUid of newDonors) {
      // Get donor info
      const donorDoc = await admin.firestore().collection("users").doc(donorUid).get();
      if (!donorDoc.exists) continue;
      const donorData = donorDoc.data();
      // Compose donor name
      const donorName = `${donorData.firstName || ""} ${donorData.lastName || ""}`.trim();
      // Determine local time (simple: use current hour)
      const hour = new Date().getHours();
      const isDaytime = hour >= 6 && hour < 18;
      const area = isDaytime ? donorData.daytimeAddress : donorData.nighttimeAddress;
      // Compose notification
      const notification = {
        notification: {
          title: "A suitable donor has confirmed availability.",
          body: `Name: ${donorName}\nArea: ${area || "Unknown"}\nKindly prepare for donation.`,
        },
        data: {
          requestId: requestId,
          donorId: donorUid,
          notificationType: "DONOR_MATCHED",
        },
        tokens: [userData.fcmToken],
      };

      const response = await admin.messaging().sendEachForMulticast(notification);
      logger.info(`FCM Response (Donor Match): Success=${response.successCount}, Failure=${response.failureCount}`);
      if (response.failureCount > 0 && response.responses[0].error) {
        logger.error("FCM Failure Details:", response.responses[0].error);
      }

      logger.info(`Notified requester (${requesterId}) of donor acceptance: ${donorName}`);

      // Create a match document in the donor's user document
      const matchRef = admin.firestore()
        .collection("users")
        .doc(donorUid)
        .collection("matches")
        .doc(requestId);

      await matchRef.set({
        status: "matched",
        providerName: providerName,
        createdAt: admin.firestore.FieldValue.serverTimestamp(),
      });
      logger.info(`Created match document for donor (${donorUid}) and request (${requestId})`);

      // Add a message to the donor's messages collection with donorId and donorName included and adjusted bloodRequest fields
      const donorDocMsg = await admin.firestore().collection("users").doc(donorUid).get();
      const donorDataMsg = donorDocMsg.exists ? donorDocMsg.data() : {};

      const messageContent = {
        bloodRequest: {
          bloodGroup: after.bloodGroup,
          component: after.component,
          createdAt: after.createdAt,
          quantity: after.quantity,
          title: after.title,
          urgency: after.urgency,
          organizationName: providerName,
          address: providerData.address || "",
          donorId: donorUid,
          donorName: donorDataMsg.firstName || "",
          id: requestId,
          requestRef: event.data.after.ref,
          providerRef: providerDocSnap.ref,
          organisationName: after.organisationName || providerName || null,
        },
        providerLocation: {
          ...providerData,
          requestRef: event.data.after.ref,
          providerRef: providerDocSnap.ref,
        },
      };

      await admin.firestore()
        .collection("donors")
        .doc(donorUid)
        .collection("messages")
        .add({
          role: "request",
          timestamp: admin.firestore.FieldValue.serverTimestamp(),
          content: messageContent,
        });
      logger.info(`Added message to donor (${donorUid}) messages collection for request (${requestId})`);
    }
    return null;
  },
);

export const onBloodRequestDeleted = onDocumentWritten(
  "healthcare_providers/{providerId}/requests/{requestId}",
  async (event) => {
    const before = event.data.before;
    const after = event.data.after;
    // Only proceed if the document is being deleted
    if (!after.exists && before.exists) {
      const requestData = before.data();
      const foundDonors = Array.isArray(requestData.foundDonors)
        ? requestData.foundDonors : [];
      if (foundDonors.length === 0) return null;
      // Fetch FCM tokens for all foundDonors
      const donorDocs = await Promise.all(
        foundDonors.map((uid) =>
          admin.firestore().collection("users").doc(uid).get(),
        ),
      );
      const tokens = donorDocs
        .map((doc) => doc.exists && doc.data().fcmToken)
        .filter(Boolean);
      if (tokens.length === 0) return null;
      // Compose notification
      const notification = {
        notification: {
          title: "Request Cancelled",
          body: "The blood donation request you were contacted for is no longer available. It may have been filled or is no longer needed. Thank you for your willingness to help.",
        },
        data: {
          requestId: event.params.requestId,
          notificationType: "REQUEST_CANCELLED",
        },
        tokens,
      };
      const response = await admin.messaging().sendEachForMulticast(notification);
      logger.info(`FCM Response (Cancellation): Success=${response.successCount}, Failure=${response.failureCount}`);
      if (response.failureCount > 0) {
        response.responses.forEach((resp, idx) => {
          if (!resp.success) {
            logger.error(`FCM Error for token at index ${idx}:`, resp.error);
          }
        });
      }
      logger.info(`Notified ${tokens.length} donors of request cancellation.`);
    }
    return null;
  },
);

export const onProviderVerificationCreated = onDocumentCreated(
  "provider_verification/{docId}",
  async (event) => {
    try {
      const docData = event.data.data();
      if (!docData) {
        logger.error("No data found in new provider_verification document.");
        return null;
      }
      // Send admin notification with the full document data as JSON
      const message = JSON.stringify(docData, null, 2);
      const sent = await sendAdminNotification(message, "Healthcare Provider Verification");
      if (sent) {
        logger.info("Admin notified of new provider verification request.");
      } else {
        logger.error("Failed to send admin notification for provider verification.");
      }
    } catch (error) {
      logger.error("Failed to notify admin on provider verification create:", error);
    }
    return null;
  },
);
