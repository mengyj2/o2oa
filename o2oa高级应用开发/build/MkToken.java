import com.x.base.core.project.config.Config;
import com.x.base.core.project.config.Token;
import com.x.base.core.project.tools.Crypto;
public class MkToken {
  public static void main(String[] a) throws Exception {
    Token t = Config.token();
    String type   = Config.person().getEncryptType();   // 默认 "" -> DES 分支
    String cipher = t.getCipher();                      // 加密 key = md5Hex(明文)
    String token  = "cipher"
        + new java.text.SimpleDateFormat("yyyyMMddHHmmss").format(new java.util.Date())
        + cipher;
    String enc = Crypto.encrypt(token, cipher, type);
    System.out.println("CIPHER=" + cipher);
    System.out.println("TOKEN=" + enc);
  }
}
