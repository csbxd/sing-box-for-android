package io.nekohasekai.sfa.vendor

import android.os.Build
import io.nekohasekai.libbox.Libbox
import io.nekohasekai.sfa.BuildConfig
import io.nekohasekai.sfa.ktx.unwrap
import io.nekohasekai.sfa.update.UpdateInfo
import io.nekohasekai.sfa.update.UpdateTrack
import io.nekohasekai.sfa.utils.HTTPClient
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.io.Closeable

class GitHubUpdateChecker : Closeable {
    companion object {
        private val RELEASES_URL = if (BuildConfig.CUSTOM_RELEASE) {
            "https://api.github.com/repos/csbxd/sing-box-for-android/releases"
        } else {
            "https://api.github.com/repos/SagerNet/sing-box/releases"
        }
        private const val METADATA_FILENAME = "SFA-version-metadata.json"
    }

    private val client = Libbox.newHTTPClient().apply {
        modernTLS()
        keepAlive()
    }

    private val json = Json { ignoreUnknownKeys = true }

    fun checkUpdate(track: UpdateTrack, githubToken: String): UpdateInfo? {
        val request = client.newRequest()
        request.setURL(
            when (track) {
                UpdateTrack.STABLE -> "$RELEASES_URL/latest"
                UpdateTrack.BETA -> "$RELEASES_URL?per_page=3"
            },
        )
        request.setHeader("Accept", "application/vnd.github+json")
        val token = githubToken.trim()
        if (token.isNotEmpty()) {
            request.setHeader("Authorization", "Bearer $token")
        }
        request.setUserAgent(HTTPClient.userAgent)
        val content = request.execute().content.unwrap
        val releases = when (track) {
            UpdateTrack.STABLE -> listOf(json.decodeFromString<GitHubRelease>(content))
            UpdateTrack.BETA -> json.decodeFromString<List<GitHubRelease>>(content)
        }
        if (BuildConfig.CUSTOM_RELEASE) {
            return checkCustomUpdate(releases)
        }
        val release = releases.filter { !it.draft }.reduceOrNull { best, candidate ->
            if (Libbox.compareSemver(candidate.version, best.version)) candidate else best
        } ?: return null
        if (!Libbox.compareSemver(release.version, BuildConfig.VERSION_NAME)) {
            return null
        }
        val metadata = downloadMetadata(release) ?: return null

        val isLegacy = Build.VERSION.SDK_INT < Build.VERSION_CODES.M
        val apkAsset = release.assets.find { asset ->
            asset.name.endsWith(".apk") &&
                !asset.name.contains("play") &&
                asset.name.contains("legacy-android-5") == isLegacy
        }

        return UpdateInfo(
            versionCode = metadata.versionCode,
            versionName = release.version,
            downloadUrl = apkAsset?.browserDownloadUrl ?: release.htmlUrl,
            releaseUrl = release.htmlUrl,
            releaseNotes = release.body,
            isPrerelease = release.prerelease,
            fileSize = apkAsset?.size ?: 0,
        )
    }

    private fun checkCustomUpdate(releases: List<GitHubRelease>): UpdateInfo? {
        // Custom cN versions are ordered by the persisted Android versionCode.
        // The upstream semver helper does not distinguish alpha.N.c1 from alpha.N.c2.
        val (release, metadata) = releases.filter { !it.draft }.mapNotNull { release ->
            downloadMetadata(release)?.let { release to it }
        }.maxByOrNull { it.second.versionCode } ?: return null
        if (metadata.versionCode <= BuildConfig.VERSION_CODE) return null
        val isLegacy = Build.VERSION.SDK_INT < Build.VERSION_CODES.N
        val apk = release.assets.find { asset ->
            asset.name.endsWith(".apk") &&
                asset.name.contains("universal") &&
                !asset.name.contains("play") &&
                asset.name.contains("legacy-android-5") == isLegacy
        } ?: return null
        return UpdateInfo(
            versionCode = metadata.versionCode,
            versionName = release.version,
            downloadUrl = apk.browserDownloadUrl,
            releaseUrl = release.htmlUrl,
            releaseNotes = release.body,
            isPrerelease = release.prerelease,
            fileSize = apk.size,
        )
    }

    private fun downloadMetadata(release: GitHubRelease): VersionMetadata? {
        val metadataAsset = release.assets.find { it.name == METADATA_FILENAME }
            ?: return null

        val request = client.newRequest()
        request.setURL(metadataAsset.browserDownloadUrl)
        request.setUserAgent(HTTPClient.userAgent)

        val response = request.execute()
        val content = response.content.unwrap

        return json.decodeFromString<VersionMetadata>(content)
    }

    override fun close() {
        client.close()
    }

    @Serializable
    data class GitHubRelease(
        @SerialName("tag_name") val tagName: String = "",
        val name: String = "",
        val body: String? = null,
        val draft: Boolean = false,
        val prerelease: Boolean = false,
        @SerialName("html_url") val htmlUrl: String = "",
        val assets: List<GitHubAsset> = emptyList(),
    ) {
        val version: String get() = tagName.removePrefix("v")
    }

    @Serializable
    data class GitHubAsset(
        val name: String = "",
        @SerialName("browser_download_url") val browserDownloadUrl: String = "",
        val size: Long = 0,
    )

    @Serializable
    data class VersionMetadata(
        @SerialName("version_code") val versionCode: Int = 0,
    )
}
