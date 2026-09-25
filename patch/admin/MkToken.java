import com.x.base.core.project.config.Config;
import com.x.base.core.project.config.Token;
import com.x.base.core.project.tools.Crypto;

public class MkToken {
  public static void main(String[] a) throws Exception {
    Token t = Config.token();
    String type  = Config.person().getEncryptType();
    String cipher = t.getCipher();          // 32位 md5
    String token = "cipher"
        + new java.text.SimpleDateFormat("yyyyMMddHHmmss").format(new java.util.Date())
        + cipher;
    String enc = Crypto.encrypt(token, cipher, type);
    System.out.print(enc);
    System.err.println("\n[plain]  " + token + "\n[cipher] " + cipher + "\n[len]    " + enc.length());
  }
}
