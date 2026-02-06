const { setGlobalOptions } = require("firebase-functions");
const { onCall, HttpsError } = require("firebase-functions/v2/https");
const { defineSecret } = require("firebase-functions/params");
const logger = require("firebase-functions/logger");
const axios = require("axios");

// Define the secret
const googlePlacesApiKey = defineSecret("GOOGLE_PLACES_API_KEY");

/**
 * STEP 1: Get Autocomplete suggestions as the user types.
 * (Returns Place IDs, but NO coordinates)
 */
/**
 * STEP 1: Get Autocomplete suggestions with broadened filters for
 * medical/address data.
 */
exports.googlePlacesAutocomplete = onCall(
  {
    secrets: [googlePlacesApiKey],
  },
  async (request) => {
    try {
      const { input, locationType, regionCode, cityContext } = request.data;
      const apiKey = googlePlacesApiKey.value();

      if (!input) {
        throw new HttpsError("invalid-argument", "Input is required.");
      }

      const requestBody = {
        input: locationType === "neighborhood" ?
          `${input}, ${cityContext}` : input,
        includedRegionCodes: [regionCode.toLowerCase()],
        languageCode: "en",
      };

      // ADJUSTED LOGIC TO PREVENT 400 ERRORS
      if (locationType === "city") {
        requestBody.includedPrimaryTypes = ["locality"];
      } else if (locationType === "neighborhood") {
        requestBody.includedPrimaryTypes = ["neighborhood", "sublocality"];
      } else {
        /**
         * For "facility" or "address" searches:
         * We use "hospital" and "medical_clinic" for your Hema app.
         * We use "establishment" as a catch-all for named places.
         * We use "address" (The correct v1 term) for specific street
         * addresses.
         */
        requestBody.includedPrimaryTypes = [
          "hospital",
          "medical_clinic",
          "establishment",
          "address",
        ];
      }

      logger.info("Calling Google Places v1", { requestBody });

      const response = await axios.post(
        "https://places.googleapis.com/v1/places:autocomplete",
        requestBody,
        {
          headers: {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": apiKey,
            // Ensure the FieldMask is exactly this
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
      // This log will help you see exactly WHAT Google is complaining about
      logger.error("Autocomplete 400 Error Detail", {
        status: error.response && error.response.status,
        data: error.response && error.response.data,
      });
      throw new HttpsError("internal", (error.response &&
        error.response.data && error.response.data.error &&
        error.response.data.error.message) || error.message);
    }
  },
);
/**
 * STEP 2: Fetch Lat/Long for the "Selected Place".
 * Call this when the user clicks a suggestion to get coordinates for the
 * database.
 */
exports.getPlaceDetails = onCall(
  {
    secrets: [googlePlacesApiKey],
  },
  async (request) => {
    try {
      const { placeId } = request.data;
      const apiKey = googlePlacesApiKey.value();

      if (!placeId) {
        throw new HttpsError("invalid-argument", "placeId is required.");
      }

      // Call the Get Place (Details) API v1
      // We use the FieldMask to ONLY request 'location' (Lat/Lng) to save
      // costs
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
        throw new HttpsError("not-found",
          "Coordinates not found for this place.");
      }

      logger.info("Coordinates Fetched Successfully", {
        placeId: placeId,
        lat: result.location.latitude,
        lng: result.location.longitude,
      });

      return {
        lat: result.location.latitude,
        lng: result.location.longitude,
        name: result.displayName.text,
      };
    } catch (error) {
      logger.error("Place Details Error", error);
      throw new HttpsError("internal", error.message);
    }
  },
);

setGlobalOptions({
  maxInstances: 10,
  timeoutSeconds: 30,
  memory: "256MiB",
});
